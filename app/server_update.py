from __future__ import annotations

import fcntl
import json
import os
import re
import socket
import subprocess
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Iterator, Literal, TypedDict


UpdateState = Literal["idle", "queued", "running", "succeeded", "failed"]
UPDATE_STATES = frozenset({"idle", "queued", "running", "succeeded", "failed"})


class UpdateStatus(TypedDict):
    state: UpdateState
    message: str
    updated_at: str | None


class ServerUpdateInProgress(Exception):
    pass


class ServerUpdateStateError(Exception):
    pass


class ServerUpdateWorkerError(Exception):
    pass


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _new_status(state: UpdateState, message: str) -> UpdateStatus:
    return {"state": state, "message": message, "updated_at": _timestamp()}


@contextmanager
def _locked_state(state_dir: Path) -> Iterator[None]:
    state_dir.mkdir(parents=True, exist_ok=True)
    with (state_dir / "lock").open("a", encoding="utf-8") as lock_file:
        os.fchmod(lock_file.fileno(), 0o666)
        fcntl.flock(lock_file, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file, fcntl.LOCK_UN)


def _read_status(state_dir: Path) -> UpdateStatus:
    try:
        value = json.loads((state_dir / "status.json").read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"state": "idle", "message": "Kein Server-Update gestartet.", "updated_at": None}
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ServerUpdateStateError("Update-Status kann nicht gelesen werden") from exc

    if not isinstance(value, dict):
        raise ServerUpdateStateError("Update-Status hat ein ungültiges Format")
    state = value.get("state")
    message = value.get("message")
    updated_at = value.get("updated_at")
    if (
        not isinstance(state, str)
        or state not in UPDATE_STATES
        or not isinstance(message, str)
        or (updated_at is not None and not isinstance(updated_at, str))
    ):
        raise ServerUpdateStateError("Update-Status hat ein ungültiges Format")
    return {"state": state, "message": message, "updated_at": updated_at}


def _write_status(state_dir: Path, status: UpdateStatus) -> None:
    with NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=state_dir,
        prefix=".status-",
        suffix=".tmp",
        delete=False,
    ) as temporary:
        json.dump(status, temporary, ensure_ascii=False)
        temporary.write("\n")
    os.chmod(temporary.name, 0o644)
    os.replace(temporary.name, state_dir / "status.json")


def get_server_update_status(state_dir: Path) -> UpdateStatus:
    with _locked_state(state_dir):
        return _read_status(state_dir)


def queue_server_update(state_dir: Path) -> UpdateStatus:
    with _locked_state(state_dir):
        current = _read_status(state_dir)
        if current["state"] in {"queued", "running"}:
            raise ServerUpdateInProgress
        status = _new_status("queued", "Update wartet auf den lokalen Updater.")
        _write_status(state_dir, status)
        return status


def _claim_queued_update(state_dir: Path) -> bool:
    with _locked_state(state_dir):
        current = _read_status(state_dir)
        if current["state"] != "queued":
            return False
        _write_status(
            state_dir,
            _new_status(
                "running",
                "Update läuft. Die App kann kurz nicht erreichbar sein.",
            ),
        )
        return True


def _recover_interrupted_update(state_dir: Path) -> None:
    with _locked_state(state_dir):
        current = _read_status(state_dir)
        if current["state"] == "running":
            _write_status(
                state_dir,
                _new_status(
                    "failed",
                    "Der Updater wurde während des Updates neu gestartet. "
                    "Prüfe die Updater-Logs und versuche es erneut.",
                ),
            )


def _finish_update(state_dir: Path, *, succeeded: bool, message: str) -> None:
    with _locked_state(state_dir):
        current = _read_status(state_dir)
        if current["state"] != "running":
            raise ServerUpdateStateError("Update wurde nicht als laufend markiert")
        status: UpdateState = "succeeded" if succeeded else "failed"
        _write_status(state_dir, _new_status(status, message))


def _compose_project_name() -> str:
    result = subprocess.run(
        [
            "docker",
            "inspect",
            "--format",
            '{{ index .Config.Labels "com.docker.compose.project" }}',
            socket.gethostname(),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    project_name = result.stdout.strip()
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", project_name):
        raise ServerUpdateWorkerError(
            "Docker-Compose-Projekt konnte nicht ermittelt werden"
        )
    return project_name


def run_pending_update(state_dir: Path, project_dir: Path) -> bool:
    _recover_interrupted_update(state_dir)
    if not _claim_queued_update(state_dir):
        return False

    step = "Docker-Verbindung"
    try:
        project_name = _compose_project_name()
        step = "Git-Pull"
        subprocess.run(["git", "pull", "--ff-only"], cwd=project_dir, check=True)
        step = "Docker-Compose-Neuaufbau"
        subprocess.run(
            [
                "docker",
                "compose",
                "--project-name",
                project_name,
                "--file",
                str(project_dir / "compose.yaml"),
                "--project-directory",
                str(project_dir),
                "up",
                "--detach",
                "--build",
                "app",
            ],
            cwd=project_dir,
            check=True,
        )
    except ServerUpdateWorkerError as exc:
        message = f"{exc}. Details: docker compose logs updater."
        print(message, file=sys.stderr, flush=True)
    except subprocess.CalledProcessError as exc:
        message = (
            f"{step} fehlgeschlagen (Exit-Code {exc.returncode}). "
            "Details: docker compose logs updater."
        )
        print(message, file=sys.stderr, flush=True)
    except OSError as exc:
        message = f"{step} konnte nicht ausgeführt werden. Details: docker compose logs updater."
        print(f"{message} ({exc})", file=sys.stderr, flush=True)
    else:
        _finish_update(
            state_dir,
            succeeded=True,
            message="Update erfolgreich abgeschlossen.",
        )
        return True

    _finish_update(state_dir, succeeded=False, message=message)
    return True


def main() -> None:
    state_dir = Path(os.environ.get("GASSI_UPDATE_STATE_DIR", "/state"))
    project_dir = Path(os.environ.get("GASSI_UPDATE_PROJECT_DIR", "/workspace"))
    while True:
        if run_pending_update(state_dir, project_dir):
            os.execv(sys.executable, [sys.executable, "-m", "app.server_update"])
        time.sleep(2)


if __name__ == "__main__":
    main()
