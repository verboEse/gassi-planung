from __future__ import annotations

import subprocess
from pathlib import Path

from fastapi.testclient import TestClient

from app import server_update
from app.auth import hash_password
from app.db import Database
from app.main import create_app


def test_server_update_is_admin_only_and_queues_once(tmp_path, monkeypatch):
    monkeypatch.setenv("GASSI_SESSION_SECRET", "test-session-secret-that-is-long-enough")
    state_dir = tmp_path / "updates"
    monkeypatch.setenv("GASSI_UPDATE_STATE_DIR", str(state_dir))
    db_path = tmp_path / "server-update.sqlite3"
    db = Database(db_path)
    db.add_account("Admin", hash_password("admin family password"))
    db.add_account("Laura", hash_password("laura family password"))
    assert db.set_admin("Admin", True)
    app = create_app(str(db_path))

    with TestClient(app) as admin_client, TestClient(app) as user_client:
        assert admin_client.post("/auth/login", json={
            "display_name": "Admin", "password": "admin family password",
        }).status_code == 200
        assert user_client.post("/auth/login", json={
            "display_name": "Laura", "password": "laura family password",
        }).status_code == 200
        assert user_client.get("/api/admin/server-update").status_code == 403
        assert user_client.post("/api/admin/server-update").status_code == 403

        assert admin_client.get("/api/admin/server-update").json()["state"] == "idle"
        queued = admin_client.post("/api/admin/server-update")
        assert queued.status_code == 202
        assert queued.json()["state"] == "queued"
        assert admin_client.post("/api/admin/server-update").status_code == 409


def test_updater_runs_only_fixed_commands_and_records_success(tmp_path, monkeypatch):
    state_dir = tmp_path / "updates"
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    server_update.queue_server_update(state_dir)
    monkeypatch.setattr(server_update, "_compose_project_name", lambda: "gassi-planung")
    commands = []

    def run(command, *, cwd, check):
        commands.append((command, cwd, check))

    monkeypatch.setattr(server_update.subprocess, "run", run)
    assert server_update.run_pending_update(state_dir, project_dir)

    assert commands == [
        (["git", "pull", "--ff-only"], project_dir, True),
        (
            [
                "docker",
                "compose",
                "--project-name",
                "gassi-planung",
                "--file",
                str(project_dir / "compose.yaml"),
                "--project-directory",
                str(project_dir),
                "up",
                "--detach",
                "--build",
                "app",
            ],
            project_dir,
            True,
        ),
    ]
    assert server_update.get_server_update_status(state_dir)["state"] == "succeeded"
    assert (state_dir / "status.json").stat().st_mode & 0o444 == 0o444


def test_updater_records_command_failure(tmp_path, monkeypatch):
    state_dir = tmp_path / "updates"
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    server_update.queue_server_update(state_dir)
    monkeypatch.setattr(server_update, "_compose_project_name", lambda: "gassi-planung")
    commands = []

    def fail_git_pull(command, *, cwd, check):
        commands.append(command)
        raise subprocess.CalledProcessError(1, command)

    monkeypatch.setattr(server_update.subprocess, "run", fail_git_pull)
    assert server_update.run_pending_update(state_dir, project_dir)

    status = server_update.get_server_update_status(state_dir)
    assert status["state"] == "failed"
    assert "Git-Pull fehlgeschlagen (Exit-Code 1)" in status["message"]
    assert commands == [["git", "pull", "--ff-only"]]
