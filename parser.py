"""Turn free-text lines into PSR ledger entries.

One entry per line. Order of words does not matter. Examples:
    Ravi credit 5000 Sri Lakshmi Stores
    ravi collected 2,000 cash from Sri Lakshmi
    12/11 Kumar cr 1.5k Balaji Traders bill 457
    yesterday Suresh received 3000 upi Ganesh Kirana note: part payment
"""
from __future__ import annotations

import re
from datetime import date, timedelta

CREDIT_WORDS = {"credit", "cr", "credited", "given", "gave", "give", "sale", "sold", "sales", "udhar", "debit", "dr"}
COLLECT_WORDS = {"collected", "collection", "collect", "coll", "received", "recd", "rcvd", "rec", "paid",
                 "payment", "pay", "got", "jama"}
MODE_WORDS = {"cash": "Cash", "upi": "UPI", "gpay": "UPI", "phonepe": "UPI", "paytm": "UPI",
              "online": "UPI", "bank": "Bank", "neft": "Bank", "imps": "Bank", "rtgs": "Bank",
              "transfer": "Bank", "cheque": "Cheque", "check": "Cheque", "chq": "Cheque"}
STOP_WORDS = {"to", "from", "by", "for", "at", "of", "the", "rs", "rs.", "inr", "amount", "amt", "on", "and",
              "in", "via", "today"}
AMOUNT_RE = re.compile(r"^(?:₹|rs\.?|inr)?(\d[\d,]*(?:\.\d+)?)(k|l|lac|lakh)?/?-?$", re.I)
DATE_RES = [
    (re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2})$"), "ymd"),
    (re.compile(r"^(\d{1,2})[/.-](\d{1,2})(?:[/.-](\d{2,4}))?$"), "dmy"),
]


def _parse_date(tok: str, today: date) -> date | None:
    t = tok.lower()
    if t == "today":
        return today
    if t in {"yesterday", "yday"}:
        return today - timedelta(days=1)
    for rx, kind in DATE_RES:
        m = rx.match(t)
        if not m:
            continue
        try:
            if kind == "ymd":
                return date(int(m[1]), int(m[2]), int(m[3]))
            y = int(m[3]) if m[3] else today.year
            y = y + 2000 if y < 100 else y
            d = date(y, int(m[2]), int(m[1]))
            if not m[3] and d > today + timedelta(days=31):   # "28/12" typed in January = last year
                d = d.replace(year=y - 1)
            return d
        except ValueError:
            return None
    return None


def _parse_amount(tok: str) -> float | None:
    m = AMOUNT_RE.match(tok.strip())
    if not m:
        return None
    v = float(m[1].replace(",", ""))
    suf = (m[2] or "").lower()
    if suf == "k":
        v *= 1_000
    elif suf in {"l", "lac", "lakh"}:
        v *= 100_000
    return round(v, 2)


def _match_psr(words: list[str], known: list[str]) -> tuple[str | None, set[int]]:
    """Find a known PSR name (full name first, then first name) in the words."""
    low = [w.lower() for w in words]
    for name in sorted(known, key=len, reverse=True):
        parts = name.lower().split()
        n = len(parts)
        for i in range(len(low) - n + 1):
            if low[i:i + n] == parts:
                return name, set(range(i, i + n))
    firsts = {}
    for name in known:
        firsts.setdefault(name.split()[0].lower(), []).append(name)
    for i, w in enumerate(low):
        if w in firsts and len(firsts[w]) == 1:
            return firsts[w][0], {i}
    return None, set()


def parse_line(line: str, known_psrs: list[str], default_date: date | None = None,
               today: date | None = None) -> dict | None:
    today = today or date.today()
    raw = line.strip()
    if not raw or raw.startswith("#"):
        return None
    text, notes = re.sub(r"[—–]", " ", raw), ""
    m = re.search(r"\s(?:note:?|notes:?|-{1,2}|//)\s+(.*)$", text, re.I)
    if m:
        notes, text = m[1].strip(), text[: m.start()]

    # reference (bill / invoice / receipt / order no.) before amount detection, so "bill 457" is not an amount
    bill = ""
    m = re.search(r"(?:\bbill|\binv(?:oice)?|\breceipt|\brcpt|\border|\bref|\bno\.?)\s*[:#]?\s*([A-Za-z0-9/-]*\d[A-Za-z0-9/-]*)"
                  r"|#\s*([A-Za-z0-9/-]+)", text, re.I)
    if m:
        bill = m[1] or m[2]
        text = text[: m.start()] + " " + text[m.end():]

    words = [w for w in re.split(r"\s+|;|,(?!\d{2,3}\b)", text) if w]   # keep "2,000" / "1,50,000" together
    words = [w.strip(".:") or w for w in words]
    used: set[int] = set()
    entry = {"entry_date": default_date or today, "psr": "", "kind": "", "amount": None, "shop": "",
             "mode": "", "bill_no": bill, "notes": notes, "raw_text": raw, "warnings": []}

    for i, w in enumerate(words):
        lw = w.lower()
        if entry["amount"] is None and (a := _parse_amount(w)) is not None and not re.match(r"^\d{1,2}[/-]\d|^\d{1,2}\.\d{1,2}\.\d", w):
            entry["amount"] = a; used.add(i); continue
        if (d := _parse_date(w, today)) is not None:
            entry["entry_date"] = d; used.add(i); continue
        if lw in CREDIT_WORDS and not entry["kind"]:
            entry["kind"] = "Credit"; used.add(i); continue
        if lw in COLLECT_WORDS and not entry["kind"]:
            entry["kind"] = "Collection"; used.add(i); continue
        if lw in MODE_WORDS and not entry["mode"]:
            entry["mode"] = MODE_WORDS[lw]; used.add(i); continue
        if lw in STOP_WORDS:
            used.add(i)

    rest = [(i, w) for i, w in enumerate(words) if i not in used]
    psr, idx = _match_psr([w for _, w in rest], known_psrs)
    if psr:
        used |= {rest[j][0] for j in idx}
    elif rest:
        psr = rest[0][1].title()
        used.add(rest[0][0])
        entry["warnings"].append(f"New PSR '{psr}'")
    entry["psr"] = psr or ""
    entry["shop"] = " ".join(w for i, w in enumerate(words) if i not in used).title()

    if entry["amount"] is None:
        entry["warnings"].append("No amount found")
    if not entry["kind"]:
        entry["kind"] = "Credit"
        entry["warnings"].append("Type not stated — assumed Credit")
    if not entry["psr"]:
        entry["warnings"].append("No PSR name")
    if entry["entry_date"] > today:
        entry["warnings"].append("Date is in the future")
    return entry


def parse_text(text: str, known_psrs: list[str], default_date: date | None = None,
               today: date | None = None) -> list[dict]:
    out = []
    for line in text.splitlines():
        e = parse_line(line, known_psrs, default_date, today)
        if e:
            out.append(e)
    return out
