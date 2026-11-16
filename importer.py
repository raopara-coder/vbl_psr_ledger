"""Import the "PSR WISE ... CREDIT LIST" Excel workbook into the ledger.

Workbook layout (one sheet per PSR, e.g. "1-PSR" ... "17-PSR", "PASHA", "CE", "YASIN", "OTHERS"):
    DATE | NAME (shop) | PSR | TOTAL BILL | PAYMENT | DUE | REMARKS
in monthly blocks: a header row, bill rows, then a subtotal row with only DUE filled.
A "TOTAL" sheet maps PSR codes to people (PSR-1 -> SIVA, CE -> GANESH, ...).

Each bill becomes a Credit entry (amount = TOTAL BILL). Money already received (PAYMENT) becomes a
Collection entry, dated by the last date written in REMARKS. Every imported entry carries a key, so
uploading a newer copy of the file only adds what changed:
  * new bills                     -> new Credit
  * a bill's PAYMENT went up      -> Collection for the difference
  * a bill no longer in the file  -> offered as "fully paid" (you decide)
"""
from __future__ import annotations

import re
from collections import Counter
from datetime import date, datetime

import pandas as pd

import db

HEAD = ["DATE", "NAME", "PSR", "TOTAL BILL", "PAYMENT", "DUE", "REMARKS"]
MONTHS = {m: i for i, m in enumerate(
    ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"], 1)}
DATE_RE = re.compile(r"(\d{1,2})[-/ ]([A-Za-z]{3,9}|\d{1,2})[-/ ,]*(\d{4})?")


# ---------------------------------------------------------------- small parsers
def _month(tok: str) -> int | None:
    if tok.isdigit():
        n = int(tok)
        return n if 1 <= n <= 12 else None
    return MONTHS.get(tok[:3].upper())


def parse_cell_date(v) -> date | None:
    """Bill date: Excel date, or text like 01/20/2026 (month first, as exported) or 15-Sep-2026."""
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    if not isinstance(v, str):
        return None
    t = v.strip().rstrip(".").strip()
    for fmt in ("%m/%d/%Y", "%d-%b-%Y", "%d-%B-%Y", "%d-%m-%Y", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(t, fmt).date()
        except ValueError:
            pass
    m = DATE_RE.fullmatch(t)
    if m and m[3] and _month(m[2]):
        try:
            return date(int(m[3]), _month(m[2]), int(m[1]))
        except ValueError:
            return None
    return None


def remark_payments(remark, bill_date: date, year_hint: int) -> tuple[date | None, str]:
    """Latest payment date written in REMARKS, and the mode of that payment if marked.
    (U) = UPI, (C) = Cash, CHQ = cheque."""
    if isinstance(remark, (datetime, date)):
        return parse_cell_date(remark), ""
    if not isinstance(remark, str):
        return None, ""
    found = []
    for m in DATE_RE.finditer(remark):
        mon = _month(m[2])
        if not mon:
            continue
        try:
            d = date(int(m[3]) if m[3] else year_hint, mon, int(m[1]))
        except ValueError:
            continue
        tail = remark[m.end():m.end() + 5].upper()
        mode = "UPI" if "(U)" in tail else "Cash" if "(C)" in tail else ""
        found.append((d, mode))
    if not found:
        return None, "Cheque" if "CHQ" in remark.upper() else ""
    d, mode = max(found, key=lambda x: x[0])
    if not mode and "CHQ" in remark.upper():
        mode = "Cheque"
    return d, mode


def _num(v) -> float:
    if v is None or v == "":
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(str(v).replace(",", "").strip() or 0)
    except ValueError:
        return float("nan")


def _norm(s) -> str:
    return " ".join(str(s or "").split()).upper()


def sheet_code(sheet: str) -> str:
    m = re.fullmatch(r"\s*(\d+)\s*-\s*PSR\s*", sheet, re.I) or re.fullmatch(r"\s*PSR\s*-?\s*(\d+)\s*", sheet, re.I)
    return f"PSR-{int(m[1])}" if m else _norm(sheet)


def snapshot_from_name(filename: str) -> date | None:
    """'... UPTO 16-SEPT-2026.xlsx' -> 2026-09-16"""
    m = re.search(r"(\d{1,2})[-_ ]([A-Za-z]{3,9})[-_ ](\d{4})", filename or "")
    if m and _month(m[2]):
        try:
            return date(int(m[3]), _month(m[2]), int(m[1]))
        except ValueError:
            return None
    return None


# ---------------------------------------------------------------- read workbook
def read_workbook(file, filename: str = "") -> dict:
    """Returns {"bills": DataFrame, "people": {code: name}, "checks": DataFrame,
    "warnings": [...], "snapshot": date}."""
    import openpyxl
    wb = openpyxl.load_workbook(file, data_only=True, read_only=True)
    snapshot = snapshot_from_name(filename) or date.today()
    people, rows, checks, warnings = {}, [], [], []

    if "TOTAL" in [s.upper() for s in wb.sheetnames]:
        ws = wb[[s for s in wb.sheetnames if s.upper() == "TOTAL"][0]]
        for r in ws.iter_rows(values_only=True):
            cells = [c for c in r if c not in (None, "")]
            if len(cells) >= 2 and isinstance(cells[0], str) and isinstance(cells[-1], str) \
                    and re.fullmatch(r"PSR-?\d+|[A-Z][A-Z ]{0,20}", cells[0].strip()) and cells[0] != cells[-1] \
                    and cells[-1].strip().upper() not in {"TOTAL", "GRAND TOTAL"}:
                people[sheet_code(cells[0])] = cells[-1].strip().title()

    for sheet in wb.sheetnames:
        if sheet.upper() == "TOTAL":
            continue
        ws, code = wb[sheet], sheet_code(sheet)
        last_total, n_bills = None, 0
        for i, r in enumerate(ws.iter_rows(values_only=True), 1):
            r = list(r) + [None] * 7
            d, name, _, bill, pay, due, remark = r[:7]
            if isinstance(d, str) and d.strip().upper() == "DATE":
                continue                                    # header row
            if d is None and not name:
                if isinstance(due, (int, float)):
                    last_total = float(due)                 # subtotal / grand total row
                continue
            bd = parse_cell_date(d)
            bill_v, pay_v, due_v = _num(bill), _num(pay), _num(due)
            where = f"{sheet} row {i}"
            if bd is None:
                warnings.append(f"{where}: date '{d}' not understood — row skipped")
                continue
            if not (bill_v > 0):
                warnings.append(f"{where}: no TOTAL BILL — row skipped")
                continue
            if pay_v != pay_v or bill_v != bill_v:
                warnings.append(f"{where}: amount not a number — row skipped")
                continue
            if due not in (None, "") and abs(bill_v - pay_v - due_v) > 0.5:
                warnings.append(f"{where} ({name}): bill {bill_v:g} − payment {pay_v:g} ≠ due {due_v:g}")
            if bd > snapshot:
                warnings.append(f"{where} ({name}): bill date {bd} is after the file date {snapshot}")
            pdate, mode = remark_payments(remark, bd, bd.year)
            if pay_v > 0 and (pdate is None or pdate < bd or pdate > snapshot):
                if pdate is not None:
                    warnings.append(f"{where} ({name}): payment date {pdate} in remarks is before the bill or "
                                    f"after the file date — used the bill date")
                pdate = bd
            rows.append({"sheet": sheet, "row": i, "code": code, "bill_date": bd, "shop": " ".join(str(name).split()),
                         "bill": round(bill_v, 2), "paid": round(pay_v, 2), "due": round(bill_v - pay_v, 2),
                         "pay_date": pdate if pay_v > 0 else None, "mode": mode,
                         "remarks": remark.strftime("%d-%b-%Y") if isinstance(remark, (datetime, date))
                         else (str(remark).strip() if remark else "")})
            n_bills += 1
        if n_bills:
            got = round(sum(x["due"] for x in rows if x["sheet"] == sheet), 2)
            checks.append({"sheet": sheet, "code": code, "person": people.get(code, ""), "bills": n_bills,
                           "due_in_rows": got, "sheet_total": last_total,
                           "ok": last_total is None or abs(got - last_total) < 1})

    bills = pd.DataFrame(rows)
    if not bills.empty:
        base = (bills["code"] + "|" + bills["bill_date"].astype(str) + "|" + bills["shop"].map(_norm) + "|"
                + bills["bill"].map(lambda v: f"{v:.2f}"))
        bills["key"] = "bill:" + base + "#" + (base.groupby(base).cumcount() + 1).astype(str)
    return {"bills": bills, "people": people, "checks": pd.DataFrame(checks), "warnings": warnings,
            "snapshot": snapshot}


# ---------------------------------------------------------------- compare with ledger
def plan(parsed: dict) -> pd.DataFrame:
    """What importing would do, as rows: action, psr, date, shop, amount, mode, notes, apply."""
    bills, snap = parsed["bills"], parsed["snapshot"]
    state = db.import_state()                       # {bill key: {"bill":..,"paid":..,"last_pay":..,"psr":..,"shop":..}}
    out = []
    psr_names = {}
    for code in sorted(set(bills["code"])) if not bills.empty else []:
        person = parsed["people"].get(code)
        psr_names[code] = person or (code if code.startswith("PSR-") else code.title())
    for b in bills.itertuples():
        psr = psr_names[b.code]
        note = b.remarks
        if b.key not in state:
            out.append(dict(action="New bill", code=b.code, psr=psr, date=b.bill_date, shop=b.shop, amount=b.bill,
                            mode="", notes=note, key=b.key, apply=True))
            if b.paid > 0:
                out.append(dict(action="Payment", code=b.code, psr=psr, date=b.pay_date, shop=b.shop,
                                amount=b.paid, mode=b.mode, notes=note, key=b.key + "|pay", apply=True))
        else:
            extra = round(b.paid - state[b.key]["paid"], 2)
            if extra > 0.004:
                last = state[b.key]["last_pay"] if isinstance(state[b.key]["last_pay"], str) else None
                d = b.pay_date if b.pay_date and (not last or str(b.pay_date) > last) else snap
                out.append(dict(action="More payment", code=b.code, psr=psr, date=d, shop=b.shop, amount=extra,
                                mode=b.mode, notes=note, key=b.key + "|pay", apply=True))
            elif extra < -0.004:
                out.append(dict(action="Check: payment went down", code=b.code, psr=psr, date=snap, shop=b.shop,
                                amount=-extra, mode="", notes=f"was {state[b.key]['paid']:g}, file says {b.paid:g}",
                                key=b.key, apply=False))
    in_file = set(bills["key"]) if not bills.empty else set()
    codes = set(bills["code"]) if not bills.empty else set()
    for key, s in state.items():
        left = round(s["bill"] - s["paid"], 2)
        if key not in in_file and left > 0.004 and key.split("|")[0][5:] in codes:
            out.append(dict(action="Not in file — mark paid?", code=key.split("|")[0][5:], psr=s["psr"], date=snap,
                            shop=s["shop"], amount=left, mode="", notes="bill no longer in the credit list",
                            key=key + "|pay", apply=False))
    cols = ["apply", "action", "psr", "code", "date", "shop", "amount", "mode", "notes", "key"]
    return pd.DataFrame(out, columns=cols)


def apply_plan(p: pd.DataFrame) -> dict:
    """Save the ticked rows. Creates PSRs as needed (area = PSR code)."""
    todo = p[(p["apply"]) & (~p["action"].str.startswith("Check"))]
    pid = {}
    for code, name in todo[["code", "psr"]].drop_duplicates().itertuples(index=False):
        pid[code] = db.get_or_create_psr_by_code(code, name)
    rows = []
    for r in todo.itertuples():
        kind = "Credit" if r.action == "New bill" else "Collection"
        rows.append(dict(entry_date=str(r.date), psr_id=pid[r.code], kind=kind, amount=float(r.amount),
                         shop=r.shop, mode=r.mode or "", bill_no="", notes=r.notes or "", src_key=r.key))
    res = db.add_entries_bulk(rows)
    c = Counter(r.action for r in todo.itertuples())
    return {**res, "by_action": dict(c), "psrs": len(pid)}
