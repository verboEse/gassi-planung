from __future__ import annotations

import argparse
import getpass
import os

from .auth import hash_password
from .db import Database


def main() -> None:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    reset = commands.add_parser("reset-password")
    reset.add_argument("username")
    grant = commands.add_parser("grant-admin")
    grant.add_argument("username")
    revoke = commands.add_parser("revoke-admin")
    revoke.add_argument("username")
    commands.add_parser("list-users")
    args = parser.parse_args()

    db = Database(os.environ.get("GASSI_DB", "gassi.sqlite3"))
    if args.command == "list-users":
        for user in db.list_admin_users():
            print(f"{user['username']}\t{'admin' if user['is_admin'] else 'user'}")
        return
    if args.command in ("grant-admin", "revoke-admin"):
        try:
            changed = db.set_admin(args.username, args.command == "grant-admin")
        except ValueError as exc:
            parser.error(str(exc))
        if not changed:
            parser.error("Teilnehmerkonto nicht gefunden")
        role = "Admin" if args.command == "grant-admin" else "Admin-Rechte entfernt für"
        print(f"{role}: {args.username}")
        return

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
