from __future__ import annotations

import argparse
import getpass
import os

from .auth import hash_password
from .db import Database


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("reset-password",))
    parser.add_argument("username")
    args = parser.parse_args()

    db = Database(os.environ.get("GASSI_DB", "gassi.sqlite3"))
    account = db.account_for_username(args.username)
    if not account:
        parser.error("Teilnehmerkonto nicht gefunden")

    password = getpass.getpass("Neues Passwort (mindestens 12 Zeichen): ")
    if len(password) < 12 or len(password) > 256:
        parser.error("Passwort muss 12 bis 256 Zeichen lang sein")
    if password != getpass.getpass("Passwort wiederholen: "):
        parser.error("Passwörter stimmen nicht überein")
    db.set_account_password(account["id"], hash_password(password))
    print(f"Passwort für {account['name']} wurde zurückgesetzt.")


if __name__ == "__main__":
    main()
