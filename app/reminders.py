from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
from collections.abc import Iterable
from datetime import date as dt_date
from datetime import datetime, timedelta, timezone

import requests
from cryptography.hazmat.primitives import serialization
from py_vapid import Vapid
from pywebpush import WebPushException, webpush

from .db import Database
from .ical import SLOT_TIMES, SLOT_LABELS, TZ

logger = logging.getLogger(__name__)


def slot_start_utc(walk_date: str, slot: str) -> datetime:
    day = dt_date.fromisoformat(walk_date)
    hour, minute = SLOT_TIMES[slot][0]
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=TZ).astimezone(
        timezone.utc
    )


def reminder_jobs(
    plans: Iterable[dict], enabled_person_ids: set[int]
) -> list[tuple[int, str, str, str]]:
    jobs: dict[tuple[int, str, str], str] = {}
    for plan in plans:
        for day in plan["days"]:
            walk_date = day["date"]
            for slot, assignment in day["slots"].items():
                person_id = assignment.get("person_id")
                if person_id not in enabled_person_ids:
                    continue
                due_at = (
                    slot_start_utc(walk_date, slot) - timedelta(minutes=15)
                ).isoformat(timespec="seconds")
                jobs[(person_id, walk_date, slot)] = due_at
    return [(*key, due_at) for key, due_at in sorted(jobs.items())]


def load_vapid_configuration() -> tuple[Vapid, str, str] | None:
    public_key = os.environ.get("GASSI_VAPID_PUBLIC_KEY", "")
    private_key_b64 = os.environ.get("GASSI_VAPID_PRIVATE_KEY_B64", "")
    subject = os.environ.get("GASSI_VAPID_SUBJECT", "")
    if not public_key or not private_key_b64 or not subject:
        return None
    try:
        private_key = base64.b64decode(private_key_b64, validate=True)
        vapid = Vapid.from_pem(private_key)
        raw_public_key = vapid.public_key.public_bytes(
            serialization.Encoding.X962,
            serialization.PublicFormat.UncompressedPoint,
        )
    except Exception:
        return None
    expected_public_key = base64.urlsafe_b64encode(raw_public_key).rstrip(b"=").decode()
    if expected_public_key != public_key:
        return None
    return vapid, subject, public_key


def send_browser_push(subscription: dict, payload: dict, vapid: Vapid, subject: str) -> None:
    webpush(
        subscription_info=subscription,
        data=json.dumps(payload, ensure_ascii=False),
        vapid_private_key=vapid,
        vapid_claims={"sub": subject},
        ttl=60,
        timeout=10,
    )


async def dispatch_due_reminders(
    db: Database,
    jobs: list[tuple[int, str, str, str]],
    enabled_person_ids: set[int],
    now: datetime,
    vapid: Vapid,
    subject: str,
    sender=send_browser_push,
) -> None:
    now = now.astimezone(timezone.utc)
    db.reconcile_reminder_outbox(jobs, now)
    active_jobs = {(person_id, walk_date, slot) for person_id, walk_date, slot, _ in jobs}
    for job in db.claim_due_reminders(now):
        reminder_id = job["id"]
        person_id = job["person_id"]
        key = (person_id, job["walk_date"], job["slot"])
        if key not in active_jobs or person_id not in enabled_person_ids or not db.reminders_enabled(person_id):
            db.finish_reminder(reminder_id, "cancelled", now)
            continue
        slot_start = slot_start_utc(job["walk_date"], job["slot"])
        if now >= slot_start:
            db.finish_reminder(reminder_id, "expired", now)
            continue
        subscriptions = db.list_push_subscriptions(person_id)
        if not subscriptions:
            db.finish_reminder(reminder_id, "cancelled", now)
            continue

        payload = {
            "title": "Gassi-Erinnerung",
            "body": f"In 15 Minuten: Gassi-Runde {SLOT_LABELS[job['slot']]}",
            "tag": f"gassi-{person_id}-{job['walk_date']}-{job['slot']}",
            "url": "/",
        }
        sent = False
        retry = False
        for subscription in subscriptions:
            try:
                await asyncio.to_thread(sender, subscription, payload, vapid, subject)
                sent = True
            except WebPushException as error:
                if error.status_code in {404, 410}:
                    db.delete_push_subscription(person_id, subscription["endpoint"])
                elif error.status_code is None or error.status_code == 429 or error.status_code >= 500:
                    retry = True
                    logger.warning("Browser-Push fehlgeschlagen (HTTP %s)", error.status_code)
                else:
                    logger.warning("Browser-Push abgelehnt (HTTP %s)", error.status_code)
            except requests.exceptions.RequestException as error:
                retry = True
                logger.warning("Browser-Push-Netzwerkfehler (%s)", type(error).__name__)
            except Exception as error:
                retry = True
                logger.warning("Browser-Push-Versandfehler (%s)", type(error).__name__)

        if retry:
            attempts = job["attempts"] + 1
            if attempts >= 3:
                db.finish_reminder(reminder_id, "cancelled", now)
            else:
                next_attempt = now + timedelta(seconds=30 * 2 ** (attempts - 1))
                if next_attempt >= slot_start:
                    db.finish_reminder(reminder_id, "expired", now)
                else:
                    db.retry_reminder(reminder_id, next_attempt, now)
        elif sent:
            db.finish_reminder(reminder_id, "sent", now)
        else:
            db.finish_reminder(reminder_id, "cancelled", now)
