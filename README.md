# VBL PSR Ledger

A Streamlit app to track **credit given to PSRs (sales representatives)** and the **payments received** back,
with balances per PSR, monthly consolidation and month archiving. Each entity (account) signs in
separately and has its own ledger.

## Pages
| Page | What it does |
|---|---|
| Overview | Totals, quick plain-text entry (`credit 12500 to Ravi — invoice 248`), PSR balances, latest transactions |
| PSR balances | Outstanding per PSR, statement with running balance, edit / archive a PSR |
| Transactions | Search and filter, edit or delete entries, CSV export |
| Monthly | Per-PSR month-end consolidation, month-by-month trend, PSR × month grid |
| Archive | Close finished months: entries are locked, saved to CSV, and still count in balances |

## Run
```bash
pip install -r requirements.txt
streamlit run app.py
```
On Windows you can double-click `Start PSR Ledger.bat`.

## Accounts (first-time setup)
Accounts are kept in `accounts.local.json`, which is **not** committed. Passwords are stored only as
salted PBKDF2 hashes. Create each entity's account once:
```bash
python accounts.py set varun Varun "Varun Beverages" <username> <password>
python accounts.py set parle Parle "Parle" <username> <password>
python accounts.py list
```
Run the same `set` command again to change a password.

## Data
- Each entity's ledger is a SQLite file: `psr_ledger_<entity>.db` (not committed — back it up yourself).
- Archived months are also copied to `archive/<entity>/*.csv`.
- Set `PSR_LEDGER_DATA` to keep the data files in another folder.

## Files
| File | Purpose |
|---|---|
| `app.py` | Streamlit front end (pages, dialogs, sign-in) |
| `db.py` | SQLite backend: PSRs, entries, reports, monthly, archive |
| `parser.py` | Turns plain-text lines into entries |
| `accounts.py` | Sign-in check and account setup command |
| `.streamlit/config.toml` | Theme |
