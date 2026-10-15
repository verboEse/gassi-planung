from __future__ import annotations

import sqlite3
import sys

from app.admin import main as admin_main
from app.auth import verify_password
from app.db import Database


def test_admin_role_is_granted_from_console(tmp_path, monkeypatch, capsys):
    path = tmp_path / "admin.sqlite3"
    db = Database(path)
    db.add_account("Jan", "unused-hash")
    monkeypatch.setenv("GASSI_DB", str(path))
    monkeypatch.setattr(sys, "argv", ["app.admin", "grant-admin", "Jan"])

    admin_main()

    assert db.account_for_username("Jan")["is_admin"] == 1
    assert "Admin: Jan" in capsys.readouterr().out


def test_migrates_existing_password_accounts_with_admin_columns(tmp_path):
    path = tmp_path / "password-accounts.sqlite3"
    with sqlite3.connect(path) as con:
        con.execute(
            "CREATE TABLE persons (id INTEGER PRIMARY KEY, name TEXT, color TEXT, active INTEGER DEFAULT 1)"
        )
        con.execute("INSERT INTO persons VALUES (1, 'Jan', '#4a90d9', 1)")
        con.execute(
            "CREATE TABLE accounts (person_id INTEGER PRIMARY KEY, username TEXT, password_hash TEXT)"
        )
        con.execute("INSERT INTO accounts VALUES (1, 'Jan', 'existing-hash')")

    db = Database(path)
    account = db.account_for_username("Jan")
    assert account["password_hash"] == "existing-hash"
    assert account["is_admin"] == 0
    assert account["auth_version"] == 1


def test_migrates_apple_account_and_allows_admin_password_reset(tmp_path, monkeypatch):
    path = tmp_path / "legacy.sqlite3"
    with sqlite3.connect(path) as con:
        con.execute(
            """
            CREATE TABLE persons (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                color TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1
            )
            """
        )
        con.execute("INSERT INTO persons (id, name, color) VALUES (1, 'Jan', '#4a90d9')")
        con.execute(
            """
            CREATE TABLE accounts (
                apple_sub TEXT PRIMARY KEY,
                person_id INTEGER NOT NULL UNIQUE REFERENCES persons(id) ON DELETE CASCADE
            )
            """
        )
        con.execute("INSERT INTO accounts VALUES ('old-apple-id', 1)")

    db = Database(path)
    account = db.account_for_username("Jan")
    assert account and account["password_hash"] == ""

    monkeypatch.setenv("GASSI_DB", str(path))
    monkeypatch.setattr(sys, "argv", ["app.admin", "reset-password", "Jan"])
    password = iter(("new admin-set password", "new admin-set password"))
    monkeypatch.setattr("app.admin.getpass.getpass", lambda _: next(password))
    admin_main()

    assert verify_password(
        "new admin-set password", db.account_for_username("Jan")["password_hash"]
    )
