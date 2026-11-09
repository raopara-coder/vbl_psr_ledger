"""Backend for the PSR ledger: SQLite file `psr_ledger.db` next to this file.

A PSR (sales representative) gives goods on credit to shops and later collects.
  Credit     -> PSR's due goes UP
  Collection -> PSR's due goes DOWN
Balance due = opening due + credits - collections.
"""
from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

# Each entity (account) has its own database file in DATA_DIR. PSR_LEDGER_DATA points the app
# at another folder (e.g. a test copy).
DATA_DIR = Path(os.environ.get("PSR_LEDGER_DATA") or Path(__file__).parent)
DB_PATH = DATA_DIR / "psr_ledger.db"      # used only when no entity is chosen (tests / scripts)
PATH_RESOLVER = None                      # app sets this: () -> Path of the signed-in entity's DB


def entity_db(entity: str) -> Path:
    return DATA_DIR / f"psr_ledger_{entity}.db"


def current_path() -> Path:
    return Path(PATH_RESOLVER() if PATH_RESOLVER else DB_PATH)


def archive_dir(path=None) -> Path:
    p = Path(path) if path else current_path()
    return p.parent / "archive" / p.stem.replace("psr_ledger_", "")
KINDS = ["Credit", "Collection"]
MODES = ["", "Cash", "UPI", "Bank", "Cheque", "Other"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS psrs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL UNIQUE COLLATE NOCASE,
    phone       TEXT DEFAULT '',
    area        TEXT DEFAULT '',
    opening_due REAL NOT NULL DEFAULT 0,
    active      INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS entries (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_date TEXT NOT NULL,
    psr_id     INTEGER NOT NULL REFERENCES psrs(id),
    shop       TEXT DEFAULT '',
    kind       TEXT NOT NULL CHECK (kind IN ('Credit','Collection')),
    amount     REAL NOT NULL CHECK (amount > 0),
    mode       TEXT DEFAULT '',
    bill_no    TEXT DEFAULT '',
    notes      TEXT DEFAULT '',
    raw_text   TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    archived   INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS archives (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    cutoff      TEXT NOT NULL,          -- last date included (month end)
    created_at  TEXT NOT NULL,
    n_entries   INTEGER NOT NULL,
    credit      REAL NOT NULL,
    collected   REAL NOT NULL,
    export_file TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS ix_entries_psr  ON entries(psr_id);
CREATE INDEX IF NOT EXISTS ix_entries_date ON entries(entry_date);
"""


@contextmanager
def connect(path=None):
    con = sqlite3.connect(path or current_path())
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def init_db(path=None) -> None:
    with connect(path) as con:
        con.executescript(SCHEMA)
        cols = [r[1] for r in con.execute("PRAGMA table_info(entries)")]
        if "archived" not in cols:   # databases created before archiving existed
            con.execute("ALTER TABLE entries ADD COLUMN archived INTEGER NOT NULL DEFAULT 0")


# -------------------------------------------------------------------- PSRs
def add_psr(name, phone="", area="", opening_due=0.0, path=None) -> int:
    name = " ".join((name or "").split()).title()
    if not name:
        raise ValueError("PSR name is required.")
    with connect(path) as con:
        return con.execute("INSERT INTO psrs(name, phone, area, opening_due) VALUES (?,?,?,?)",
                           (name, phone, area, round(float(opening_due), 2))).lastrowid


def get_or_create_psr(name, path=None) -> int:
    with connect(path) as con:
        row = con.execute("SELECT id FROM psrs WHERE name=?", (name.strip(),)).fetchone()
    return row["id"] if row else add_psr(name, path=path)


def update_psr(pid, path=None, **fields) -> None:
    fields = {k: v for k, v in fields.items() if k in {"name", "phone", "area", "opening_due", "active"}}
    if fields:
        with connect(path) as con:
            con.execute(f"UPDATE psrs SET {', '.join(f'{k}=?' for k in fields)} WHERE id=?",
                        (*fields.values(), pid))


def delete_psr(pid, path=None) -> None:
    with connect(path) as con:
        if con.execute("SELECT COUNT(*) FROM entries WHERE psr_id=?", (pid,)).fetchone()[0]:
            raise ValueError("This PSR has entries — mark inactive instead of deleting.")
        con.execute("DELETE FROM psrs WHERE id=?", (pid,))


def psrs(active_only=False, path=None) -> pd.DataFrame:
    with connect(path) as con:
        return pd.read_sql_query("SELECT * FROM psrs" + (" WHERE active=1" if active_only else "")
                                 + " ORDER BY name", con)


# ----------------------------------------------------------------- entries
def add_entry(entry_date, psr_id, kind, amount, shop="", mode="", bill_no="", notes="",
              raw_text="", path=None) -> int:
    if kind not in KINDS:
        raise ValueError(f"Type must be one of {KINDS}.")
    if float(amount) <= 0:
        raise ValueError("Amount must be more than 0.")
    _check_open(entry_date, path)
    with connect(path) as con:
        return con.execute(
            "INSERT INTO entries(entry_date, psr_id, shop, kind, amount, mode, bill_no, notes, raw_text,"
            " created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (str(entry_date), int(psr_id), (shop or "").strip().title(), kind, round(float(amount), 2),
             mode or "", bill_no or "", notes or "", raw_text or "",
             datetime.now().isoformat(timespec="seconds")),
        ).lastrowid


def update_entry(eid, path=None, **fields) -> None:
    ok = {"entry_date", "psr_id", "shop", "kind", "amount", "mode", "bill_no", "notes"}
    fields = {k: v for k, v in fields.items() if k in ok}
    with connect(path) as con:
        row = con.execute("SELECT archived FROM entries WHERE id=?", (eid,)).fetchone()
    if row and row[0]:
        raise ValueError("This entry is archived — restore the archive first to change it.")
    if "entry_date" in fields:
        _check_open(fields["entry_date"], path)
    if fields:
        with connect(path) as con:
            con.execute(f"UPDATE entries SET {', '.join(f'{k}=?' for k in fields)} WHERE id=?",
                        (*fields.values(), eid))


def delete_entry(eid, path=None) -> None:
    with connect(path) as con:
        if con.execute("DELETE FROM entries WHERE id=? AND archived=0", (eid,)).rowcount == 0:
            raise ValueError("Archived entries can't be deleted.")


def entries(psr_id=None, start=None, end=None, kind=None, archived=False, path=None) -> pd.DataFrame:
    """archived: False = live entries only, True = archived only, None = both."""
    q = ("SELECT e.id, e.entry_date, p.name AS psr, p.area, e.psr_id, e.shop, e.kind, e.amount, e.mode,"
         " e.bill_no, e.notes, e.created_at, e.archived FROM entries e JOIN psrs p ON p.id=e.psr_id WHERE 1=1")
    args = []
    if archived is not None:
        q += " AND e.archived=?"; args.append(int(bool(archived)))
    if psr_id:
        q += " AND e.psr_id=?"; args.append(int(psr_id))
    if start:
        q += " AND e.entry_date>=?"; args.append(str(start))
    if end:
        q += " AND e.entry_date<=?"; args.append(str(end))
    if kind:
        q += " AND e.kind=?"; args.append(kind)
    q += " ORDER BY e.entry_date DESC, e.id DESC"
    with connect(path) as con:
        return pd.read_sql_query(q, con, params=args)


def known_shops(path=None) -> list[str]:
    with connect(path) as con:
        return [r[0] for r in con.execute("SELECT DISTINCT shop FROM entries WHERE shop<>'' ORDER BY shop")]


# ----------------------------------------------------------------- reports
def psr_summary(as_of=None, path=None) -> pd.DataFrame:
    """One row per PSR: opening, credit, collected, balance due, last credit/collection."""
    as_of = str(as_of or date.today())
    q = """
    SELECT p.id, p.name AS psr, p.area, p.phone, p.active, p.opening_due AS opening,
      COALESCE(SUM(CASE WHEN e.kind='Credit'     THEN e.amount END), 0) AS credit,
      COALESCE(SUM(CASE WHEN e.kind='Collection' THEN e.amount END), 0) AS collected,
      COUNT(e.id) AS entries,
      MAX(CASE WHEN e.kind='Credit'     THEN e.entry_date END) AS last_credit,
      MAX(CASE WHEN e.kind='Collection' THEN e.entry_date END) AS last_collection
    FROM psrs p LEFT JOIN entries e ON e.psr_id=p.id AND e.entry_date<=?
    GROUP BY p.id ORDER BY p.name
    """
    with connect(path) as con:
        df = pd.read_sql_query(q, con, params=(as_of,))
    df["due"] = (df["opening"] + df["credit"] - df["collected"]).round(2)
    last = pd.to_datetime(df["last_collection"].fillna(df["last_credit"]), errors="coerce")
    df["days_since_collection"] = (pd.Timestamp(as_of) - last).dt.days
    return df.sort_values("due", ascending=False).reset_index(drop=True)


def shop_summary(psr_id=None, path=None) -> pd.DataFrame:
    q = ("SELECT p.name AS psr, e.shop,"
         " SUM(CASE WHEN e.kind='Credit' THEN e.amount ELSE 0 END) AS credit,"
         " SUM(CASE WHEN e.kind='Collection' THEN e.amount ELSE 0 END) AS collected,"
         " MAX(e.entry_date) AS last_entry"
         " FROM entries e JOIN psrs p ON p.id=e.psr_id"
         + (" WHERE e.psr_id=?" if psr_id else "") + " GROUP BY p.name, e.shop")
    with connect(path) as con:
        df = pd.read_sql_query(q, con, params=(int(psr_id),) if psr_id else ())
    df["shop"] = df["shop"].replace("", "(no shop)")
    df["due"] = (df["credit"] - df["collected"]).round(2)
    return df.sort_values("due", ascending=False).reset_index(drop=True)


def ledger(psr_id, start=None, end=None, path=None) -> pd.DataFrame:
    """Statement for one PSR, oldest first, with running balance due."""
    with connect(path) as con:
        opening = con.execute("SELECT opening_due FROM psrs WHERE id=?", (int(psr_id),)).fetchone()[0]
    e = entries(psr_id=psr_id, archived=None, path=path).iloc[::-1].reset_index(drop=True)
    e["Credit"] = e["amount"].where(e["kind"] == "Credit", 0.0)
    e["Collection"] = e["amount"].where(e["kind"] == "Collection", 0.0)
    e["Balance due"] = (opening + (e["Credit"] - e["Collection"]).cumsum()).round(2)
    bf = opening
    if start:
        before = e[e["entry_date"] < str(start)]
        bf = before["Balance due"].iloc[-1] if len(before) else opening
        e = e[e["entry_date"] >= str(start)]
    if end:
        e = e[e["entry_date"] <= str(end)]
    head = pd.DataFrame([{"entry_date": str(start) if start else "", "shop": "Opening / brought forward",
                          "Credit": 0.0, "Collection": 0.0, "Balance due": round(bf, 2)}])
    cols = ["id", "entry_date", "shop", "bill_no", "mode", "notes", "Credit", "Collection", "Balance due"]
    return pd.concat([head, e[cols]], ignore_index=True)[cols]


def daily(start=None, end=None, path=None) -> pd.DataFrame:
    q = ("SELECT entry_date AS date,"
         " SUM(CASE WHEN kind='Credit' THEN amount ELSE 0 END) AS credit,"
         " SUM(CASE WHEN kind='Collection' THEN amount ELSE 0 END) AS collected,"
         " COUNT(*) AS entries FROM entries WHERE entry_date BETWEEN ? AND ?"
         " GROUP BY entry_date ORDER BY entry_date")
    with connect(path) as con:
        return pd.read_sql_query(q, con, params=(str(start or "0000"), str(end or "9999")))


def totals(start=None, end=None, path=None) -> dict:
    d = daily(start, end, path)
    return {"credit": float(d["credit"].sum()), "collected": float(d["collected"].sum()),
            "entries": int(d["entries"].sum())}


# ------------------------------------------------------------------ monthly
def _month_bounds(month: str) -> tuple[str, str]:
    y, m = map(int, month.split("-"))
    start = date(y, m, 1)
    nxt = date(y + (m == 12), m % 12 + 1, 1)
    return str(start), str(nxt - timedelta(days=1))


def month_label(month: str) -> str:
    return datetime.strptime(month, "%Y-%m").strftime("%b %Y")


def months_available(path=None) -> list[str]:
    """Every month from the first entry to this month, newest first."""
    with connect(path) as con:
        first = con.execute("SELECT MIN(entry_date) FROM entries").fetchone()[0]
    cur = date.today().replace(day=1)
    m = min(date.fromisoformat(first).replace(day=1), cur) if first else cur
    out = []
    while m <= cur:
        out.append(m.strftime("%Y-%m"))
        m = date(m.year + (m.month == 12), m.month % 12 + 1, 1)
    return out[::-1]


def monthly_psr(month: str, path=None) -> pd.DataFrame:
    """Consolidation for one month, per PSR: opening, credit, payments, closing outstanding."""
    start, end = _month_bounds(month)
    q = """
    SELECT p.id, p.name AS psr, p.area, p.active,
      p.opening_due + COALESCE(SUM(CASE WHEN e.entry_date < :s THEN
            CASE e.kind WHEN 'Credit' THEN e.amount ELSE -e.amount END END), 0) AS opening,
      COALESCE(SUM(CASE WHEN e.entry_date BETWEEN :s AND :e AND e.kind='Credit' THEN e.amount END), 0) AS credit,
      COALESCE(SUM(CASE WHEN e.entry_date BETWEEN :s AND :e AND e.kind='Collection' THEN e.amount END), 0) AS collected,
      COUNT(CASE WHEN e.entry_date BETWEEN :s AND :e THEN 1 END) AS entries
    FROM psrs p LEFT JOIN entries e ON e.psr_id=p.id
    GROUP BY p.id ORDER BY p.name
    """
    with connect(path) as con:
        df = pd.read_sql_query(q, con, params={"s": start, "e": end})
    df["closing"] = (df["opening"] + df["credit"] - df["collected"]).round(2)
    df["opening"] = df["opening"].round(2)
    keep = (df["active"] == 1) | (df[["opening", "credit", "collected", "closing"]].abs().sum(axis=1) > 0)
    return df[keep].sort_values("closing", ascending=False).reset_index(drop=True)


def monthly_overview(path=None) -> pd.DataFrame:
    """One row per month (newest first): opening, credit, payments, net, closing outstanding."""
    months = months_available(path)[::-1]
    with connect(path) as con:
        opening = con.execute("SELECT COALESCE(SUM(opening_due),0) FROM psrs").fetchone()[0]
        g = pd.read_sql_query(
            "SELECT substr(entry_date,1,7) AS month,"
            " SUM(CASE WHEN kind='Credit' THEN amount ELSE 0 END) AS credit,"
            " SUM(CASE WHEN kind='Collection' THEN amount ELSE 0 END) AS collected,"
            " COUNT(*) AS entries, COUNT(DISTINCT psr_id) AS psrs FROM entries GROUP BY month", con)
    df = pd.DataFrame({"month": months}).merge(g, on="month", how="left").fillna(0)
    df["net"] = df["credit"] - df["collected"]
    df["closing"] = (opening + df["net"].cumsum()).round(2)
    df["opening"] = (df["closing"] - df["net"]).round(2)
    df["collection_pct"] = (df["collected"] / df["credit"].where(df["credit"] > 0) * 100).round(1)
    df[["entries", "psrs"]] = df[["entries", "psrs"]].astype(int)
    cols = ["month", "opening", "credit", "collected", "net", "closing", "collection_pct", "entries", "psrs"]
    return df[cols].iloc[::-1].reset_index(drop=True)


def psr_month_matrix(value="closing", last_n=12, path=None) -> pd.DataFrame:
    """PSR x month grid. value: 'closing' (outstanding at month end), 'credit' or 'collected'."""
    months = months_available(path)[:last_n][::-1]
    rows = [monthly_psr(m, path).assign(month=m)[["psr", "month", value]] for m in months]
    if not rows:
        return pd.DataFrame()
    t = pd.concat(rows).pivot_table(index="psr", columns="month", values=value, aggfunc="sum", fill_value=0)
    return t.reindex(columns=months, fill_value=0).round(2).reset_index()


# ------------------------------------------------------------------ archive
def closed_until(path=None) -> str | None:
    """Last date covered by an archive (entries on/before it are locked)."""
    with connect(path) as con:
        return con.execute("SELECT MAX(cutoff) FROM archives").fetchone()[0]


def _check_open(entry_date, path=None) -> None:
    cut = closed_until(path)
    if cut and str(entry_date) <= cut:
        raise ValueError(f"Months up to {cut} are archived (closed). Use a later date, "
                         "or restore the archive first.")


def archive_preview(month: str, path=None) -> dict:
    _, end = _month_bounds(month)
    with connect(path) as con:
        r = con.execute("SELECT COUNT(*), COALESCE(SUM(CASE WHEN kind='Credit' THEN amount END),0),"
                        " COALESCE(SUM(CASE WHEN kind='Collection' THEN amount END),0)"
                        " FROM entries WHERE archived=0 AND entry_date<=?", (end,)).fetchone()
    return {"cutoff": end, "entries": r[0], "credit": r[1], "collected": r[2]}


def archive_through(month: str, path=None) -> dict:
    """Close every month up to and including `month`. Its entries are locked, hidden from the
    day-to-day screens and saved to archive/<file>.csv. They still count in balances and reports."""
    if month >= date.today().strftime("%Y-%m"):
        raise ValueError("You can only archive months that have ended.")
    pv = archive_preview(month, path)
    cut = closed_until(path)
    if cut and pv["cutoff"] <= cut:
        raise ValueError(f"Already archived up to {cut}.")
    rows = entries(end=pv["cutoff"], archived=False, path=path)
    adir = archive_dir(path)
    adir.mkdir(parents=True, exist_ok=True)
    fname = f"psr_entries_upto_{month}_{datetime.now():%Y%m%d_%H%M%S}.csv"
    rows.to_csv(adir / fname, index=False)
    with connect(path) as con:
        con.execute("UPDATE entries SET archived=1 WHERE archived=0 AND entry_date<=?", (pv["cutoff"],))
        con.execute("INSERT INTO archives(cutoff, created_at, n_entries, credit, collected, export_file)"
                    " VALUES (?,?,?,?,?,?)", (pv["cutoff"], datetime.now().isoformat(timespec="seconds"),
                                              pv["entries"], pv["credit"], pv["collected"], fname))
    return {**pv, "file": fname}


def archives(path=None) -> pd.DataFrame:
    with connect(path) as con:
        return pd.read_sql_query("SELECT * FROM archives ORDER BY cutoff DESC", con)


def restore_last_archive(path=None) -> str | None:
    """Undo the most recent archive: its entries become editable again. The CSV copy is kept."""
    with connect(path) as con:
        rows = con.execute("SELECT id, cutoff FROM archives ORDER BY cutoff DESC LIMIT 2").fetchall()
        if not rows:
            return None
        prev_cut = rows[1]["cutoff"] if len(rows) > 1 else "0000-00-00"
        con.execute("UPDATE entries SET archived=0 WHERE archived=1 AND entry_date>?", (prev_cut,))
        con.execute("DELETE FROM archives WHERE id=?", (rows[0]["id"],))
        return rows[0]["cutoff"]
