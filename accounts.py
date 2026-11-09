"""Sign-in accounts. One account per entity; each entity has its own ledger file.

Accounts live in `accounts.local.json` next to this file. That file is NOT in git, so
usernames and password hashes never reach GitHub. Passwords are stored only as salted
PBKDF2-SHA256 hashes.

Create or change an account (also the way to change a password):
    python accounts.py set <entity> <label> "<full name>" <username> <password>
    e.g. python accounts.py set parle Parle "Parle" vbl_psr_parle <password>
List accounts:
    python accounts.py list
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import sys
from pathlib import Path

ITERATIONS = 200_000
ACCOUNTS_FILE = Path(os.environ.get("PSR_LEDGER_ACCOUNTS") or Path(__file__).with_name("accounts.local.json"))


def load() -> dict:
    if not ACCOUNTS_FILE.exists():
        return {}
    return json.loads(ACCOUNTS_FILE.read_text(encoding="utf-8"))


ACCOUNTS = load()


def hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or os.urandom(16)
    return salt.hex() + "$" + hashlib.pbkdf2_hmac("sha256", password.encode(), salt, ITERATIONS).hex()


def check(entity: str, username: str, password: str) -> bool:
    acc = ACCOUNTS.get(entity)
    if not acc or not hmac.compare_digest(username.strip().lower(), acc["username"]):
        hash_password(password)  # same work either way, so timing gives nothing away
        return False
    salt_hex, want = acc["hash"].split("$")
    got = hash_password(password, bytes.fromhex(salt_hex)).split("$")[1]
    return hmac.compare_digest(got, want)


def set_account(entity, label, full_name, username, password) -> None:
    data = load()
    data[entity] = {"label": label, "full_name": full_name, "username": username.strip().lower(),
                    "hash": hash_password(password)}
    ACCOUNTS_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


if __name__ == "__main__":
    args = sys.argv[1:]
    if args[:1] == ["set"] and len(args) == 6:
        set_account(*args[1:])
        print(f"Saved account '{args[1]}' in {ACCOUNTS_FILE.name}")
    elif args[:1] == ["list"]:
        for k, v in load().items():
            print(f"{k:10} {v['label']:12} {v['username']}")
    else:
        sys.exit(__doc__)
