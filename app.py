"""PSR Ledger — credit given to sales representatives (PSRs) and payments received back.

Run from this folder:  streamlit run app.py   (or double-click "Start PSR Ledger.bat")
"""
from __future__ import annotations

import html
from datetime import date, datetime, timedelta

import pandas as pd
import streamlit as st

import db
from parser import parse_text

import accounts

accounts.ACCOUNTS = accounts.load()   # re-read every run, so Secrets edited on Streamlit Cloud apply at once

APP_NAME = "VBL PSR Ledger"
st.set_page_config(page_title=APP_NAME, page_icon="📒", layout="wide")

# every database call goes to the signed-in entity's own file
db.PATH_RESOLVER = lambda: (db.entity_db(st.session_state["entity"]) if st.session_state.get("entity")
                            else db.DB_PATH)

KIND_LABEL = {"Credit": "Credit", "Collection": "Payment"}
TYPE_OPTIONS = {"Credit given": "Credit", "Payment received": "Collection"}

# ---------------------------------------------------------------------- styles
st.html("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Figtree:wght@400;500;600;700&display=swap');
.stApp, .stApp p, .stApp label, .stApp input, .stApp textarea, .stApp td, .stApp th, .stApp li
  { font-family: 'Figtree', system-ui, sans-serif; }
.block-container { padding-top: 2.2rem; max-width: 1280px; }
header[data-testid="stHeader"] { background: transparent; }

/* sidebar */
[data-testid="stSidebar"] { min-width: 270px; }
.fn-brand { display:flex; gap:12px; align-items:center; margin: 4px 0 30px; }
.fn-logo { width:46px; height:46px; border-radius:12px; background:#1f5c40; display:flex; align-items:center;
           justify-content:center; font-size:22px; color:#fff; }
.fn-brand b { font-size:20px; color:#fff; display:block; line-height:1.1; }
.fn-brand span { font-size:13px; color:#a9bdb0; }
.fn-side-label { font-size:11px; letter-spacing:.12em; font-weight:700; color:#8fa799; margin:0 0 8px 4px; }
.fn-side-note { font-size:12.5px; color:#9fb5a7; border-top:1px solid #24402f; padding-top:16px; margin-top:22px; }
.fn-user { display:flex; gap:10px; align-items:center; border-top:1px solid #24402f; padding-top:16px; margin-top:30px; }
.fn-user .fn-av { background:#e3ece6; }
.fn-user b { color:#fff; font-size:12.5px; display:block; word-break:break-all; }
.fn-user span { color:#9fb5a7; font-size:12px; }
[data-testid="stSidebar"] [class*="st-key-nav_"] button { width:100%; justify-content:flex-start; padding:10px 14px;
     border-radius:10px; font-size:15.5px; border:none; }
[data-testid="stSidebar"] [class*="st-key-nav_"] button[kind="tertiary"] { color:#d5e2da; }
[data-testid="stSidebar"] [class*="st-key-nav_"] button[kind="tertiary"]:hover { background:#18352a; color:#fff; }
[data-testid="stSidebar"] [class*="st-key-nav_"] button[kind="primary"] { background:#1d3d2d; color:#fff; font-weight:600; }
[data-testid="stSidebar"] [class*="st-key-nav_"] button p { font-size:15.5px; }
[data-testid="stSidebar"] [class*="st-key-nav_"] button > div { justify-content:flex-start; width:100%; gap:12px; }

/* Credit given / Payment received toggle: selected side dark green like the design */
[data-testid="stButtonGroup"] button[kind="segmented_controlActive"] { background:#1f5c40; color:#fff; border-color:#1f5c40; }
[data-testid="stButtonGroup"] button { padding:10px 0; }

/* headings */
.fn-eyebrow { font-size:11.5px; letter-spacing:.12em; font-weight:700; color:#5d7466; margin:26px 0 2px; }
.fn-h2 { font-size:25px; font-weight:700; color:#16241c; margin:0 0 6px; }
.fn-h1 { font-size:30px; font-weight:700; color:#16241c; margin:0; }
.fn-sub { color:#5d7466; font-size:14px; margin:2px 0 14px; }

/* cards */
[class*="st-key-card"] { background:#fbfdfb; border:1px solid #dbe4dd; border-radius:14px; padding:18px 22px; }
.fn-qe-title { display:flex; gap:12px; align-items:center; }
.fn-qe-icon { width:40px; height:40px; border-radius:10px; background:#f6ead9; display:flex; align-items:center;
              justify-content:center; font-size:18px; }
.fn-qe-title b { font-size:16.5px; color:#16241c; } .fn-qe-title span { display:block; font-size:12.5px; color:#5d7466; }

.fn-kpis { display:grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap:14px; margin: 10px 0 4px; }
.fn-kpi { background:#fbfdfb; border:1px solid #dbe4dd; border-radius:14px; padding:16px 18px; }
.fn-kpi .l { font-size:12px; color:#5d7466; font-weight:600; letter-spacing:.04em; text-transform:uppercase; }
.fn-kpi .v { font-size:25px; font-weight:700; color:#16241c; margin-top:4px; }
.fn-kpi .s { font-size:12.5px; color:#6c8275; margin-top:2px; }
.fn-kpi .v.red { color:#c8452a; } .fn-kpi .v.green { color:#237a4b; }

/* tables */
.fn-table-wrap { background:#fbfdfb; border:1px solid #dbe4dd; border-radius:14px; overflow-x:auto; }
table.fn { width:100%; border-collapse:collapse; font-size:14px; }
table.fn th { text-align:left; font-size:11.5px; font-weight:700; color:#4d6357; padding:14px 12px;
              border-bottom:1px solid #dbe4dd; white-space:nowrap; }
table.fn td { padding:13px 12px; border-bottom:1px solid #e6ede8; color:#16241c; vertical-align:middle; }
table.fn tr:last-child td { border-bottom:none; }
table.fn tr.total td { background:#eef4f0; font-weight:700; }
table.fn .r { text-align:right; } table.fn .c { text-align:center; }
.fn-who { display:flex; align-items:center; gap:12px; }
.fn-av { width:36px; height:36px; border-radius:50%; background:#e3ece6; color:#1f3d2d; font-weight:700;
         display:flex; align-items:center; justify-content:center; font-size:14px; flex:none; }
.fn-who b { font-weight:600; } .fn-who small { display:block; color:#6c8275; font-size:11.5px; }
.fn-count { background:#e6eee8; border-radius:6px; padding:3px 9px; font-size:12px; color:#3d5546; }
.fn-red { color:#c8452a; font-weight:600; } .fn-green { color:#237a4b; } .fn-greenb { color:#1f5c40; font-weight:700; }
.fn-pill { display:inline-block; padding:4px 13px; border-radius:999px; font-size:11.5px; font-weight:700; }
.fn-pill.credit { background:#d65a2c; color:#fff; }
.fn-pill.pay { background:#dcefe2; color:#1f5c40; } .fn-pill.pay:before { content:"● "; font-size:9px; }
.fn-pill.arch { background:#ece7dc; color:#6b5a35; margin-left:6px; }
.fn-date small { display:block; color:#6c8275; font-size:11.5px; }
.fn-muted { color:#6c8275; font-size:12.5px; }
.fn-empty { padding:26px; text-align:center; color:#6c8275; }
.fn-foot { border-top:1px solid #dbe4dd; margin-top:34px; padding-top:12px; font-size:12px; color:#6c8275;
           display:flex; justify-content:space-between; }
</style>
""")


# --------------------------------------------------------------------- helpers
def esc(x) -> str:
    return html.escape("" if x is None or (isinstance(x, float) and pd.isna(x)) else str(x))


def fmt(x) -> str:
    return f"{float(x or 0):,.2f}"


def avatar(name, sub="") -> str:
    initial = esc((name or "?")[:1].upper())
    sub_html = f"<small>{esc(sub)}</small>" if sub else ""
    return f'<div class="fn-who"><div class="fn-av">{initial}</div><div><b>{esc(name)}</b>{sub_html}</div></div>'


def nice_date(d) -> str:
    dt = pd.to_datetime(d)
    return f'<div class="fn-date">{dt:%b} {dt.day}, {dt.year}<small>{dt:%a}</small></div>'


def heading(eyebrow: str, title: str):
    st.html(f'<div class="fn-eyebrow">{esc(eyebrow)}</div><div class="fn-h2">{esc(title)}</div>')


def kpis(items: list[tuple]):
    """items: (label, value, sub, colour_class)"""
    cells = "".join(f'<div class="fn-kpi"><div class="l">{esc(l)}</div><div class="v {c}">{esc(v)}</div>'
                    f'<div class="s">{esc(s)}</div></div>' for l, v, s, c in items)
    st.html(f'<div class="fn-kpis">{cells}</div>')


def table(head: list[tuple[str, str]], rows: list[list[str]], empty="Nothing here yet.", total: list[str] | None = None):
    """head: (label, css class). rows: already-escaped cell html."""
    th = "".join(f'<th class="{c}">{esc(h)}</th>' for h, c in head)
    if not rows:
        body = f'<tr><td colspan="{len(head)}" class="fn-empty">{esc(empty)}</td></tr>'
    else:
        body = "".join("<tr>" + "".join(f'<td class="{head[i][1]}">{cell}</td>' for i, cell in enumerate(r))
                       + "</tr>" for r in rows)
    if total:
        body += '<tr class="total">' + "".join(f'<td class="{head[i][1]}">{cell}</td>'
                                               for i, cell in enumerate(total)) + "</tr>"
    st.html(f'<div class="fn-table-wrap"><table class="fn"><thead><tr>{th}</tr></thead>'
            f'<tbody>{body}</tbody></table></div>')


def outstanding_cell(x) -> str:
    cls = "fn-red" if x > 0.004 else "fn-greenb"
    return f'<span class="{cls}">{fmt(x)}</span>'


def psr_names(active_only=True) -> list[str]:
    return db.psrs(active_only=active_only)["name"].tolist()


def psr_ids() -> dict[str, int]:
    p = db.psrs()
    return dict(zip(p["name"], p["id"]))


def flash(msg: str, icon="✅"):
    st.session_state["flash"] = (msg, icon)


def csv_button(df: pd.DataFrame, name: str, label="Download CSV", key=None):
    st.download_button(label, df.to_csv(index=False).encode("utf-8"), name, "text/csv",
                       icon=":material/download:", key=key)


# --------------------------------------------------------------------- dialogs
@st.dialog("New transaction", width="medium")
def entry_dialog(prefill: dict | None = None):
    p = prefill or {}
    st.caption("Record credit given or a payment received from a PSR.")
    kind_label = "Payment received" if p.get("kind") == "Collection" else "Credit given"
    t = st.segmented_control("Type", list(TYPE_OPTIONS), default=kind_label, key="dlg_type",
                             label_visibility="collapsed", width="stretch")
    names = psr_names()
    psr_default = p.get("psr") or None
    if psr_default and psr_default not in names:
        names = names + [psr_default]
    psr = st.selectbox("PSR", names, index=names.index(psr_default) if psr_default else None,
                       placeholder="Choose or type a new PSR", accept_new_options=True, key="dlg_psr")
    c1, c2 = st.columns(2)
    amount = c1.number_input("Amount", min_value=0.0, value=float(p.get("amount") or 0), step=100.0,
                             format="%.2f", key="dlg_amt")
    d = c2.date_input("Date", p.get("entry_date") or date.today(), format="DD/MM/YYYY", key="dlg_date")
    c1, c2 = st.columns(2)
    shops = db.known_shops()
    shop_default = p.get("shop") or None
    if shop_default and shop_default not in shops:
        shops = shops + [shop_default]
    shop = c1.selectbox("Shop / customer (optional)", shops,
                        index=shops.index(shop_default) if shop_default else None,
                        placeholder="Type or choose", accept_new_options=True, key="dlg_shop")
    mode = c2.selectbox("Payment mode (optional)", db.MODES, index=db.MODES.index(p.get("mode") or ""),
                        key="dlg_mode", format_func=lambda m: m or "—")
    ref = st.text_input("Reference (optional)", p.get("bill_no", ""), placeholder="Invoice, receipt, or order",
                        key="dlg_ref")
    notes = st.text_area("Notes (optional)", p.get("notes", ""), placeholder="Add context for this entry",
                         height=80, key="dlg_notes")
    for w in p.get("warnings") or []:
        st.caption(f"⚠️ {w}")
    b1, b2 = st.columns([1, 1])
    if b1.button("Cancel", width="stretch", key="dlg_cancel"):
        st.rerun()
    if b2.button("Save entry", type="primary", width="stretch", key="dlg_save"):
        if not psr:
            st.error("Choose a PSR.")
        elif amount <= 0:
            st.error("Enter an amount above 0.")
        elif not t:
            st.error("Choose Credit given or Payment received.")
        else:
            try:
                pid = db.get_or_create_psr(psr)
                db.add_entry(d, pid, TYPE_OPTIONS[t], amount, shop or "", mode, ref, notes, p.get("raw_text", ""))
                flash(f"Saved: {psr} — {t.lower()} {fmt(amount)}")
                st.rerun()
            except ValueError as ex:
                st.error(str(ex))


@st.dialog("Add a PSR")
def add_psr_dialog():
    st.caption("Keep one balance history for each sales representative.")
    name = st.text_input("Representative name", placeholder="e.g. Ravi Kumar", key="ap_name")
    area = st.text_input("Area or reference (optional)", placeholder="e.g. KPHB", key="ap_area")
    c1, c2 = st.columns(2)
    phone = c1.text_input("Phone (optional)", key="ap_phone")
    opening = c2.number_input("Opening due (optional)", value=0.0, step=100.0, key="ap_open",
                              help="What this PSR already owed before you started using the app.")
    b1, b2 = st.columns(2)
    if b1.button("Cancel", width="stretch", key="ap_cancel"):
        st.rerun()
    if b2.button("Add PSR", type="primary", width="stretch", key="ap_save", disabled=not name.strip()):
        try:
            db.add_psr(name, phone, area, opening)
            flash(f"Added PSR {name.strip().title()}")
            st.rerun()
        except Exception as ex:
            st.error("A PSR with that name already exists." if "UNIQUE" in str(ex) else str(ex))


# ---------------------------------------------------------------- shared blocks
def quick_entry_card():
    def _review():
        line = st.session_state.get("qe_line", "").strip()
        if line:
            rows = parse_text(line, psr_names(active_only=False))
            if rows:
                st.session_state["qe_pending"] = rows[0]
            st.session_state["qe_line"] = ""

    with st.container(key="card_qe"):
        st.html('<div class="fn-qe-title"><div class="fn-qe-icon">✨</div><div><b>Quick entry</b>'
                '<span>Type a credit or payment in plain text, then review before saving.</span></div></div>')
        c1, c2 = st.columns([5, 1], vertical_alignment="bottom")
        c1.text_input("Quick entry", key="qe_line", label_visibility="collapsed",
                      placeholder="credit 12500 to Ravi — invoice 248   ·   Ravi paid 5000 cash Sri Lakshmi Stores")
        c2.button("Review entry", icon=":material/auto_awesome:", width="stretch", on_click=_review, key="qe_btn")
        with st.expander("Paste many entries at once (one per line)"):
            bulk_entry()
    if pending := st.session_state.pop("qe_pending", None):
        entry_dialog(pending)


def bulk_entry():
    st.caption("Examples: `Ravi credit 5000 Sri Lakshmi Stores` · `yesterday Kumar paid 2,000 upi` · "
               "`12/11 Suresh cr 1.5k Balaji Traders bill 457 note: festival stock`")
    default_date = st.date_input("Date for lines without a date", date.today(), format="DD/MM/YYYY", key="bulk_d")
    text = st.text_area("Entries", height=140, key="bulk_text", label_visibility="collapsed",
                        placeholder="One entry per line")
    if st.button("Read entries", key="bulk_read"):
        st.session_state["bulk_rows"] = parse_text(text, psr_names(active_only=False), default_date)
    rows = st.session_state.get("bulk_rows")
    if not rows:
        return
    df = pd.DataFrame(rows)
    df["warnings"] = df["warnings"].apply("; ".join)
    df["entry_date"] = pd.to_datetime(df["entry_date"]).dt.date
    df["type"] = df["kind"].map({v: k for k, v in TYPE_OPTIONS.items()})
    options = sorted(set(psr_names(active_only=False)) | (set(df["psr"].dropna()) - {""}))
    edited = st.data_editor(
        df[["entry_date", "psr", "type", "amount", "shop", "mode", "bill_no", "notes", "warnings"]],
        hide_index=True, width="stretch", num_rows="dynamic", key="bulk_editor",
        column_config={
            "entry_date": st.column_config.DateColumn("Date", format="DD/MM/YYYY", required=True),
            "psr": st.column_config.SelectboxColumn("PSR", options=options, required=True),
            "type": st.column_config.SelectboxColumn("Type", options=list(TYPE_OPTIONS), required=True),
            "amount": st.column_config.NumberColumn("Amount", min_value=0.01, format="%.2f", required=True),
            "shop": "Shop / customer", "mode": st.column_config.SelectboxColumn("Mode", options=db.MODES),
            "bill_no": "Reference", "notes": "Notes",
            "warnings": st.column_config.TextColumn("Check", disabled=True)})
    new = sorted(set(edited["psr"].dropna()) - set(psr_names(active_only=False)) - {""})
    if new:
        st.info("New PSRs will be created: **" + ", ".join(new) + "**")
    c1, c2 = st.columns([1, 4])
    if c1.button(f"Save {len(edited)} entries", type="primary", key="bulk_save"):
        saved, errs = 0, []
        for n, r in edited.reset_index(drop=True).iterrows():
            try:
                if not r["psr"] or pd.isna(r["amount"]):
                    raise ValueError("needs PSR and amount")
                db.add_entry(r["entry_date"] or date.today(), db.get_or_create_psr(str(r["psr"])),
                             TYPE_OPTIONS.get(r["type"], "Credit"), r["amount"], r["shop"] or "",
                             r["mode"] or "", r["bill_no"] or "", r["notes"] or "",
                             df["raw_text"].iloc[n] if n < len(df) else "")
                saved += 1
            except Exception as ex:
                errs.append(f"Row {n + 1}: {ex}")
        st.session_state.pop("bulk_rows", None)
        flash(f"Saved {saved} entries." + (f" Skipped {len(errs)}." if errs else ""))
        if errs:
            st.session_state["flash_err"] = " · ".join(errs)
        st.rerun()
    if c2.button("Clear", key="bulk_clear"):
        st.session_state.pop("bulk_rows", None)
        st.rerun()


def balances_table(show_archived=False):
    s = db.psr_summary()
    if not show_archived:
        s = s[s["active"] == 1]
    s = s.sort_values("psr", key=lambda c: c.str.lower())
    rows = [[avatar(r.psr, r.area), f'<span class="fn-count">{r.entries}</span>', fmt(r.opening + r.credit),
             f'<span class="fn-green">{fmt(r.collected)}</span>', outstanding_cell(r.due)]
            for r in s.itertuples()]
    total = None
    if len(s) > 1:
        total = ["Total", f'<span class="fn-count">{s["entries"].sum()}</span>', fmt((s.opening + s.credit).sum()),
                 fmt(s.collected.sum()), outstanding_cell(s.due.sum())]
    table([("Representative", ""), ("Entries", "c"), ("Credit given", "r"), ("Payments", "r"),
           ("Outstanding", "r")], rows, "No PSRs yet — click Add PSR.", total)


def history_table(e: pd.DataFrame, limit=200):
    shown = e.head(limit)
    rows = []
    for r in shown.itertuples():
        pill = ('<span class="fn-pill credit">Credit</span>' if r.kind == "Credit"
                else '<span class="fn-pill pay">Payment</span>')
        if r.archived:
            pill += '<span class="fn-pill arch">Archived</span>'
        details = esc(r.shop) or '<span class="fn-muted">—</span>'
        extra = " · ".join(esc(x) for x in [r.bill_no, r.mode, r.notes] if x)
        if extra:
            details += f'<br><span class="fn-muted">{extra}</span>'
        amt = (f'<span class="fn-red">+{fmt(r.amount)}</span>' if r.kind == "Credit"
               else f'<span class="fn-greenb">-{fmt(r.amount)}</span>')
        rows.append([nice_date(r.entry_date), avatar(r.psr), pill, details, amt])
    table([("Date", ""), ("Representative", ""), ("Type", ""), ("Details", ""), ("Amount", "r")], rows,
          "No transactions match.")
    if len(e) > limit:
        st.caption(f"Showing the latest {limit} of {len(e)} entries — narrow the filters or download the CSV.")


def history_filters(prefix: str, with_dates=False):
    cols = st.columns([4, 1.4, 1.4] + ([1.2, 1.2] if with_dates else []))
    q = cols[0].text_input("Search", placeholder="Search shop, notes or references", key=f"{prefix}_q",
                           label_visibility="collapsed", icon=":material/search:")
    psr = cols[1].selectbox("PSR", ["All PSRs"] + psr_names(active_only=False), key=f"{prefix}_psr",
                            label_visibility="collapsed")
    kind = cols[2].selectbox("Type", ["All entries", "Credit", "Payment"], key=f"{prefix}_kind",
                             label_visibility="collapsed")
    start = end = None
    if with_dates:
        start = cols[3].date_input("From", date.today().replace(day=1), format="DD/MM/YYYY", key=f"{prefix}_s",
                                   label_visibility="collapsed")
        end = cols[4].date_input("To", date.today(), format="DD/MM/YYYY", key=f"{prefix}_e",
                                 label_visibility="collapsed")
    return q, psr, kind, start, end


def filtered_entries(q, psr, kind, start=None, end=None, archived=False) -> pd.DataFrame:
    e = db.entries(psr_ids().get(psr) if psr != "All PSRs" else None, start, end,
                   {"Credit": "Credit", "Payment": "Collection"}.get(kind), archived=archived)
    if q:
        hay = (e["shop"] + " " + e["bill_no"] + " " + e["notes"] + " " + e["psr"]).str.lower()
        e = e[hay.str.contains(q.lower(), regex=False)]
    return e


def footer():
    cut = db.closed_until()
    right = f"Archived up to {pd.to_datetime(cut):%d %b %Y}" if cut else "Credit adds to a PSR's outstanding; payments reduce it"
    who = accounts.ACCOUNTS[st.session_state["entity"]]["full_name"]
    st.html(f'<div class="fn-foot"><span>{esc(who)} ledger · stored on this computer ({db.current_path().name})</span>'
            f'<span>{esc(right)}</span></div>')


# ======================================================================== pages
def page_overview():
    today = date.today()
    st.html(f'<div class="fn-h1">Overview</div><div class="fn-sub">{today:%A, %d %B %Y}</div>')
    s = db.psr_summary()
    m = db.monthly_psr(today.strftime("%Y-%m"))
    t = db.totals(today, today)
    kpis([("Total outstanding", fmt(s["due"].sum()), f"{(s['due'] > 0.004).sum()} PSRs owe", "red"),
          ("Credit given · this month", fmt(m["credit"].sum()), f"Today {fmt(t['credit'])}", ""),
          ("Payments · this month", fmt(m["collected"].sum()), f"Today {fmt(t['collected'])}", "green"),
          ("Active PSRs", str(int((s["active"] == 1).sum())), f"{t['entries']} entries today", "")])
    st.write("")
    quick_entry_card()

    c1, c2 = st.columns([5, 1], vertical_alignment="bottom")
    with c1:
        heading("YOUR PEOPLE", "PSR balances")
    if c2.button("Add PSR", icon=":material/add:", width="stretch", key="ov_add_psr"):
        add_psr_dialog()
    balances_table()

    c1, c2 = st.columns([5, 1], vertical_alignment="bottom")
    with c1:
        heading("LATEST RECORDS", "Transaction history")
    if c2.button("New entry", icon=":material/add:", width="stretch", key="ov_new"):
        entry_dialog()
    q, psr, kind, *_ = history_filters("ov")
    history_table(filtered_entries(q, psr, kind), limit=15)
    footer()


def page_balances():
    c1, c2 = st.columns([5, 1], vertical_alignment="bottom")
    with c1:
        st.html('<div class="fn-h1">PSR balances</div><div class="fn-sub">What each representative owes today, '
                'including archived months.</div>')
    if c2.button("Add PSR", icon=":material/add:", width="stretch", key="bal_add"):
        add_psr_dialog()
    show_arch = st.toggle("Show archived PSRs", key="bal_arch")
    balances_table(show_arch)
    s = db.psr_summary()
    csv_button(s[["psr", "area", "phone", "opening", "credit", "collected", "due", "entries", "last_credit",
                  "last_collection", "active"]], f"psr_balances_{date.today()}.csv")

    names = s.sort_values("psr")["psr"].tolist()
    if not names:
        return
    heading("STATEMENT", "PSR ledger")
    c = st.columns([2, 1, 1])
    pick = c[0].selectbox("PSR", names, key="bal_pick")
    start = c[1].date_input("From", date.today() - timedelta(days=90), format="DD/MM/YYYY", key="bal_s")
    end = c[2].date_input("To", date.today(), format="DD/MM/YYYY", key="bal_e")
    pid = psr_ids()[pick]
    lg = db.ledger(pid, start, end)
    body = lg.iloc[1:]
    kpis([("Brought forward", fmt(lg["Balance due"].iloc[0]), f"before {start:%d %b %Y}", ""),
          ("Credit given", fmt(body["Credit"].sum()), "in period", ""),
          ("Payments", fmt(body["Collection"].sum()), "in period", "green"),
          ("Closing outstanding", fmt(lg["Balance due"].iloc[-1]), f"on {end:%d %b %Y}", "red")])
    rows = [[nice_date(start), '<span class="fn-muted">Opening / brought forward</span>', "", "",
             f"<b>{fmt(lg['Balance due'].iloc[0])}</b>"]]
    for r in body.rename(columns={"Balance due": "bal"}).itertuples():
        det = esc(r.shop) or "—"
        extra = " · ".join(esc(x) for x in [r.bill_no, r.mode, r.notes] if x)
        if extra:
            det += f'<br><span class="fn-muted">{extra}</span>'
        rows.append([nice_date(r.entry_date), det,
                     f'<span class="fn-red">{fmt(r.Credit)}</span>' if r.Credit else "",
                     f'<span class="fn-green">{fmt(r.Collection)}</span>' if r.Collection else "",
                     outstanding_cell(r.bal)])
    table([("Date", ""), ("Details", ""), ("Credit", "r"), ("Payment", "r"), ("Balance", "r")], rows)
    csv_button(lg.drop(columns="id"), f"ledger_{pick}_{start}_{end}.csv", key="bal_csv")

    with st.expander(f"Edit {pick}'s details or archive this PSR"):
        p = db.psrs().set_index("id").loc[pid]
        with st.form("edit_psr"):
            c = st.columns(4)
            name = c[0].text_input("Name", p["name"])
            area = c[1].text_input("Area", p["area"])
            phone = c[2].text_input("Phone", p["phone"])
            opening = c[3].number_input("Opening due", value=float(p["opening_due"]), step=100.0)
            if st.form_submit_button("Save details", type="primary"):
                try:
                    db.update_psr(pid, name=name.strip().title(), area=area, phone=phone, opening_due=opening)
                    flash("PSR details saved.")
                    st.rerun()
                except Exception as ex:
                    st.error(str(ex))
        if p["active"]:
            st.caption("Archiving a PSR hides them from day-to-day screens. Their history and balance are kept.")
            if st.button(f"Archive {pick}", icon=":material/archive:", key="bal_arch_psr"):
                db.update_psr(pid, active=0)
                flash(f"{pick} archived.")
                st.rerun()
        elif st.button(f"Restore {pick}", icon=":material/unarchive:", key="bal_unarch_psr"):
            db.update_psr(pid, active=1)
            flash(f"{pick} restored.")
            st.rerun()


def page_transactions():
    c1, c2 = st.columns([5, 1], vertical_alignment="bottom")
    with c1:
        st.html('<div class="fn-h1">Transactions</div><div class="fn-sub">Every credit and payment. '
                'Search, filter, edit or delete.</div>')
    if c2.button("New entry", icon=":material/add:", width="stretch", key="tx_new"):
        entry_dialog()
    q, psr, kind, start, end = history_filters("tx", with_dates=True)
    inc_arch = st.toggle("Include archived months", key="tx_arch")
    e = filtered_entries(q, psr, kind, start, end, archived=None if inc_arch else False)
    cr = e.loc[e.kind == "Credit", "amount"].sum()
    py = e.loc[e.kind == "Collection", "amount"].sum()
    kpis([("Entries", str(len(e)), f"{start:%d %b} – {end:%d %b %Y}", ""),
          ("Credit given", fmt(cr), "", ""), ("Payments", fmt(py), "", "green"),
          ("Net change", fmt(cr - py), "credit − payments", "red" if cr - py > 0 else "green")])
    history_table(e)
    out = e.assign(type=e["kind"].map(KIND_LABEL))[["entry_date", "psr", "area", "type", "amount", "shop", "mode",
                                                     "bill_no", "notes", "archived"]]
    csv_button(out, f"transactions_{start}_{end}.csv", key="tx_csv")

    live = e[e["archived"] == 0]
    with st.expander(f"Edit or delete entries ({len(live)} editable)"):
        if live.empty:
            st.caption("No editable entries in this filter. Archived entries are locked.")
            return
        ed = live.assign(entry_date=pd.to_datetime(live["entry_date"]).dt.date, type=live["kind"].map(
            {v: k for k, v in TYPE_OPTIONS.items()}), delete=False)
        cols = ["id", "entry_date", "psr", "type", "amount", "shop", "mode", "bill_no", "notes", "delete"]
        edited = st.data_editor(ed[cols], hide_index=True, width="stretch", key="tx_editor", column_config={
            "id": st.column_config.NumberColumn("ID", disabled=True),
            "entry_date": st.column_config.DateColumn("Date", format="DD/MM/YYYY"),
            "psr": st.column_config.SelectboxColumn("PSR", options=psr_names(active_only=False)),
            "type": st.column_config.SelectboxColumn("Type", options=list(TYPE_OPTIONS)),
            "amount": st.column_config.NumberColumn("Amount", min_value=0.01, format="%.2f"),
            "mode": st.column_config.SelectboxColumn("Mode", options=db.MODES),
            "shop": "Shop", "bill_no": "Reference", "notes": "Notes",
            "delete": st.column_config.CheckboxColumn("Delete?")})
        n_del = int(edited["delete"].sum())
        if n_del:
            st.warning(f"{n_del} entries ticked for deletion — removed when you press Save changes.")
        if st.button("Save changes", type="primary", key="tx_save"):
            ids, orig, changed, errs = psr_ids(), ed.set_index("id"), 0, []
            for r in edited.itertuples():
                try:
                    if r.delete:
                        db.delete_entry(int(r.id))
                        continue
                    o = orig.loc[r.id]
                    f = {k: getattr(r, k) for k in ["shop", "amount", "mode", "bill_no", "notes"]
                         if getattr(r, k) != o[k]}
                    if r.entry_date != o["entry_date"]:
                        f["entry_date"] = str(r.entry_date)
                    if r.type != o["type"]:
                        f["kind"] = TYPE_OPTIONS[r.type]
                    if r.psr != o["psr"]:
                        f["psr_id"] = ids[r.psr]
                    if f:
                        db.update_entry(int(r.id), **f)
                        changed += 1
                except ValueError as ex:
                    errs.append(f"ID {r.id}: {ex}")
            flash(f"Updated {changed}, deleted {n_del} entries.")
            if errs:
                st.session_state["flash_err"] = " · ".join(errs)
            st.rerun()


def page_monthly():
    st.html('<div class="fn-h1">Monthly</div><div class="fn-sub">Month-end consolidation per PSR and '
            'month-by-month trend. Includes archived months.</div>')
    months = db.months_available()
    c1, _ = st.columns([1, 3])
    month = c1.selectbox("Month", months, format_func=db.month_label, key="mo_pick")
    m = db.monthly_psr(month)
    op, cr, py, cl = m["opening"].sum(), m["credit"].sum(), m["collected"].sum(), m["closing"].sum()
    pct = f"{py / cr * 100:.0f}% of credit" if cr else "no credit this month"
    kpis([("Opening outstanding", fmt(op), f"1 {db.month_label(month)}", ""),
          ("Credit given", fmt(cr), f"{int(m['entries'].sum())} entries", ""),
          ("Payments", fmt(py), pct, "green"),
          ("Closing outstanding", fmt(cl), f"{fmt(cl - op)} change", "red" if cl > 0.004 else "green")])

    heading("CONSOLIDATION", f"{db.month_label(month)} by PSR")
    rows = [[avatar(r.psr, r.area), f'<span class="fn-count">{r.entries}</span>', fmt(r.opening),
             fmt(r.credit), f'<span class="fn-green">{fmt(r.collected)}</span>', outstanding_cell(r.closing)]
            for r in m.itertuples()]
    total = ["Total", f'<span class="fn-count">{int(m["entries"].sum())}</span>', fmt(op), fmt(cr), fmt(py),
             outstanding_cell(cl)] if len(m) > 1 else None
    table([("Representative", ""), ("Entries", "c"), ("Opening", "r"), ("Credit given", "r"),
           ("Payments", "r"), ("Closing", "r")], rows, "No PSRs yet.", total)
    csv_button(m[["psr", "area", "opening", "credit", "collected", "closing", "entries"]],
               f"consolidation_{month}.csv", key="mo_csv1")

    heading("TREND", "Month by month")
    ov = db.monthly_overview()
    chart = ov.head(12).rename(columns={"credit": "Credit given", "collected": "Payments"})
    st.bar_chart(chart, x="month", y=["Credit given", "Payments"], stack=False, color=["#d65a2c", "#2f8a57"],
                 height=260, x_label="", y_label="")
    rows = [[f"<b>{db.month_label(r.month)}</b>", fmt(r.opening), fmt(r.credit),
             f'<span class="fn-green">{fmt(r.collected)}</span>', fmt(r.net), outstanding_cell(r.closing),
             "—" if pd.isna(r.collection_pct) else f"{r.collection_pct:.0f}%", str(r.entries)]
            for r in ov.itertuples()]
    table([("Month", ""), ("Opening", "r"), ("Credit given", "r"), ("Payments", "r"), ("Net", "r"),
           ("Closing", "r"), ("Collected %", "r"), ("Entries", "r")], rows)
    csv_button(ov, "monthly_overview.csv", key="mo_csv2")

    heading("GRID", "PSR × month")
    what = st.segmented_control("Show", ["Outstanding at month end", "Credit given", "Payments"],
                                default="Outstanding at month end", key="mo_grid")
    val = {"Outstanding at month end": "closing", "Credit given": "credit", "Payments": "collected"}[what or
                                                                                                    "Outstanding at month end"]
    grid = db.psr_month_matrix(val)
    if not grid.empty:
        grid = grid.rename(columns={c: db.month_label(c) for c in grid.columns if c != "psr"} | {"psr": "PSR"})
        st.dataframe(grid, hide_index=True, width="stretch",
                     column_config={c: st.column_config.NumberColumn(format="%.2f") for c in grid.columns[1:]})
        csv_button(grid, f"psr_by_month_{val}.csv", key="mo_csv3")
    footer()


def page_archive():
    st.html('<div class="fn-h1">Archive</div><div class="fn-sub">Close finished months so day-to-day screens '
            'stay short. Archived entries are locked, saved to a CSV file, and still count in balances and '
            'monthly reports. You can restore the latest archive.</div>')
    cut = db.closed_until()
    this_month = date.today().strftime("%Y-%m")
    ended = [m for m in db.months_available() if m < this_month and (not cut or m > cut[:7])]
    live = db.entries(archived=False)
    kpis([("Archived up to", pd.to_datetime(cut).strftime("%d %b %Y") if cut else "Nothing yet", "", ""),
          ("Live entries", str(len(live)), "shown on Overview / Transactions", ""),
          ("Archived entries", str(len(db.entries(archived=True))), "locked", "")])

    heading("CLOSE MONTHS", "Archive")
    with st.container(key="card_arch"):
        if not ended:
            st.caption("No finished months left to archive. The current month can be archived after it ends.")
        else:
            month = st.selectbox("Archive everything up to and including", ended, format_func=db.month_label,
                                 key="ar_month")
            pv = db.archive_preview(month)
            st.write(f"This will lock **{pv['entries']} entries** dated on or before "
                     f"**{pd.to_datetime(pv['cutoff']):%d %b %Y}** (credit {fmt(pv['credit'])}, "
                     f"payments {fmt(pv['collected'])}). After this, new entries can't be dated in those months.")
            ok = st.checkbox("I understand — archive these months", key="ar_ok")
            if st.button("Archive", type="primary", icon=":material/archive:", disabled=not ok, key="ar_go"):
                try:
                    r = db.archive_through(month)
                    flash(f"Archived {r['entries']} entries up to {r['cutoff']}. Copy saved: archive/{r['file']}")
                    st.rerun()
                except ValueError as ex:
                    st.error(str(ex))

    a = db.archives()
    heading("HISTORY", "Past archives")
    rows = [[f"<b>{pd.to_datetime(r.cutoff):%d %b %Y}</b>", esc(r.created_at.replace("T", " ")),
             str(r.n_entries), fmt(r.credit), fmt(r.collected), f'<span class="fn-muted">{esc(r.export_file)}</span>']
            for r in a.itertuples()]
    table([("Up to", ""), ("Archived on", ""), ("Entries", "r"), ("Credit", "r"), ("Payments", "r"),
           ("CSV copy (archive folder)", "")], rows, "No archives yet.")
    if not a.empty:
        c1, c2 = st.columns(2)
        with c1:
            arch = db.entries(archived=True)
            out = arch.assign(type=arch["kind"].map(KIND_LABEL))[
                ["entry_date", "psr", "area", "type", "amount", "shop", "mode", "bill_no", "notes"]]
            csv_button(out, "archived_entries.csv", "Download all archived entries", key="ar_csv")
        with c2:
            with st.popover("Restore latest archive", icon=":material/unarchive:"):
                st.write(f"Unlock entries archived up to **{pd.to_datetime(a['cutoff'].iloc[0]):%d %b %Y}** "
                         "so they can be edited again. The CSV copy is kept.")
                if st.button("Restore", type="primary", key="ar_restore"):
                    c = db.restore_last_archive()
                    flash(f"Restored archive up to {c}.")
                    st.rerun()

    heading("PEOPLE", "Archived PSRs")
    p = db.psr_summary()
    p = p[p["active"] == 0]
    rows = [[avatar(r.psr, r.area), outstanding_cell(r.due)] for r in p.itertuples()]
    table([("Representative", ""), ("Outstanding", "r")], rows,
          "No archived PSRs. Archive one from PSR balances → Edit details.")
    for r in p.itertuples():
        if st.button(f"Restore {r.psr}", key=f"ar_psr_{r.id}", icon=":material/unarchive:"):
            db.update_psr(r.id, active=1)
            flash(f"{r.psr} restored.")
            st.rerun()
    footer()


# ======================================================================== shell
PAGES = {
    "Overview": (":material/space_dashboard:", page_overview),
    "PSR balances": (":material/group:", page_balances),
    "Transactions": (":material/receipt_long:", page_transactions),
    "Monthly": (":material/calendar_month:", page_monthly),
    "Archive": (":material/inventory_2:", page_archive),
}
MAX_TRIES, LOCK_SECONDS = 5, 60


def login_page():
    st.html("""<style>
      [data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"], [data-testid="stExpandSidebarButton"]
        { display:none; }
      .block-container { max-width: 460px; padding-top: 9vh; }
      .fn-login-head { text-align:center; margin-bottom:18px; }
      .fn-login-head .fn-logo { margin:0 auto 12px; width:56px; height:56px; font-size:26px; }
      .fn-login-head b { font-size:26px; color:#16241c; display:block; }
      .fn-login-head span { color:#5d7466; font-size:14px; }
    </style>""")
    st.html(f'<div class="fn-login-head"><div class="fn-logo">₹</div><b>{APP_NAME}</b>'
            '<span>Sign in to your entity\'s ledger</span></div>')
    if not accounts.ACCOUNTS:
        st.error("No sign-in accounts found.\n\n"
                 "**On Streamlit Cloud:** app menu → Settings → Secrets, paste the `[accounts.…]` block, Save.\n\n"
                 "**On your PC:** run `python accounts.py set <entity> <label> \"<full name>\" <username> <password>` "
                 "in the app folder. See README.md.")
        return
    locked_until = st.session_state.get("lock_until")
    with st.container(key="card_login"):
        with st.form("login", border=False):
            entity = st.selectbox("Entity name", list(accounts.ACCOUNTS),
                                  format_func=lambda k: accounts.ACCOUNTS[k]["label"])
            user = st.text_input("Username", autocomplete="username")
            pw = st.text_input("Password", type="password", autocomplete="current-password")
            go = st.form_submit_button("Sign in", type="primary", width="stretch")
        if go:
            if locked_until and datetime.now() < locked_until:
                st.error(f"Too many wrong tries. Wait {int((locked_until - datetime.now()).total_seconds())} "
                         "seconds and try again.")
            elif accounts.check(entity, user, pw):
                for k in list(st.session_state):
                    del st.session_state[k]
                st.session_state.update(entity=entity, username=user.strip().lower(), page="Overview")
                db.init_db()
                st.rerun()
            else:
                n = st.session_state.get("bad_tries", 0) + 1
                st.session_state["bad_tries"] = n
                if n >= MAX_TRIES:
                    st.session_state["lock_until"] = datetime.now() + timedelta(seconds=LOCK_SECONDS)
                    st.session_state["bad_tries"] = 0
                st.error("Entity, username or password is not right.")


def logout():
    for k in list(st.session_state):
        del st.session_state[k]


if not st.session_state.get("entity"):
    login_page()
    st.stop()

ACC = accounts.ACCOUNTS[st.session_state["entity"]]
if "page" not in st.session_state:
    st.session_state["page"] = "Overview"


def _go(p):
    st.session_state["page"] = p


with st.sidebar:
    st.html(f'<div class="fn-brand"><div class="fn-logo">₹</div><div><b>{APP_NAME}</b>'
            f'<span>{esc(ACC["full_name"])} · PSR credit ledger</span></div></div>'
            '<div class="fn-side-label">WORKSPACE</div>')
    for name, (icon, _) in PAGES.items():
        st.button(name, icon=icon, key=f"nav_{name.replace(' ', '_')}", on_click=_go, args=(name,),
                  type="primary" if st.session_state["page"] == name else "tertiary", width="stretch")
    st.html('<div class="fn-side-note">🛡️ Each entity\'s ledger is separate and stored only on this computer.</div>'
            f'<div class="fn-user"><div class="fn-av">{esc(ACC["label"][:1])}</div><div>'
            f'<b>{esc(st.session_state["username"])}</b><span>{esc(ACC["full_name"])}</span></div></div>')
    st.button("Sign out", icon=":material/logout:", key="nav_signout", on_click=logout, type="tertiary",
              width="stretch")

if msg := st.session_state.pop("flash", None):
    st.toast(msg[0], icon=msg[1])
if err := st.session_state.pop("flash_err", None):
    st.error(err)

PAGES[st.session_state["page"]][1]()
