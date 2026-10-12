"""iCal-Export (RFC 5545) pro Person: die eigenen Gassi-Slots als Kalender-Feed.

Bewusst ohne externe iCal-Bibliothek implementiert – das Format ist für diesen
Anwendungsfall überschaubar und so bleibt die App dependency-arm.

* Zeiten werden lokal (Europe/Berlin) definiert und korrekt nach UTC
  konvertiert – inkl. Sommer-/Winterzeit via zoneinfo.
* UIDs sind stabil (Datum + Slot + Person), damit Kalender-Clients bei
  Abonnements Updates sauber zusammenführen können.
"""
from __future__ import annotations

from datetime import date as dt_date
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from .scheduler import SLOT_LABELS, Assignment

TZ = ZoneInfo("Europe/Berlin")

#: Zeitfenster der Slots (lokale Zeit Europe/Berlin): slot -> ((start_h, start_m), (end_h, end_m))
SLOT_TIMES: dict[str, tuple[tuple[int, int], tuple[int, int]]] = {
    "morning": ((6, 0), (8, 0)),
    "noon": ((12, 0), (14, 0)),
    "evening": ((18, 0), (20, 0)),
}

PRODID = "-//verboEse//gassi-planung//DE"


def escape_text(text: str) -> str:
    """Escapet TEXT-Werte nach RFC 5545 §3.3.11."""
    return (
        text.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\n", "\\n")
    )


def fold_line(line: str) -> str:
    """Faltet eine Content-Line auf max. 75 Oktette (RFC 5545 §3.1).

    Fortsetzungszeilen beginnen mit einem Leerzeichen. Es wird nie mitten in
    einem UTF-8-Mehrbytezeichen geschnitten.
    """
    encoded = line.encode("utf-8")
    if len(encoded) <= 75:
        return line
    chunks: list[str] = []
    first = True
    while encoded:
        limit = 75 if first else 74  # Folgezeilen tragen 1 Space als Prefix
        cut = min(limit, len(encoded))
        # Nicht mitten in einem UTF-8-Zeichen schneiden:
        # Continuation-Bytes haben das Muster 10xxxxxx.
        while 0 < cut < len(encoded) and (encoded[cut] & 0xC0) == 0x80:
            cut -= 1
        chunks.append(encoded[:cut].decode("utf-8"))
        encoded = encoded[cut:]
        first = False
    return "\r\n ".join(chunk for chunk in chunks)


def build_ics(person_id: int, person_name: str, assignments: list[Assignment]) -> str:
    """Baut den kompletten Kalender (VCALENDAR) für eine Person.

    :param assignments: nur die Slots, die dieser Person zugewiesen sind
    """
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:{PRODID}",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{escape_text(f'Gassi – {person_name}')}",
    ]
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    for a in sorted(assignments, key=lambda x: (x.date, x.slot)):
        (sh, sm), (eh, em) = SLOT_TIMES[a.slot]
        d = dt_date.fromisoformat(a.date)
        start = datetime(d.year, d.month, d.day, sh, sm, tzinfo=TZ).astimezone(timezone.utc)
        end = datetime(d.year, d.month, d.day, eh, em, tzinfo=TZ).astimezone(timezone.utc)
        lines += [
            "BEGIN:VEVENT",
            f"UID:gassi-{a.date}-{a.slot}-{person_id}@gassi-planung",
            f"DTSTAMP:{stamp}",
            f"DTSTART:{start:%Y%m%dT%H%M%SZ}",
            f"DTEND:{end:%Y%m%dT%H%M%SZ}",
            f"SUMMARY:{escape_text(f'🐕 Gassi – {SLOT_LABELS[a.slot]}')}",
            f"DESCRIPTION:{escape_text(f'Gassi-Runde {SLOT_LABELS[a.slot]} (Priorität {a.pref}) – zugewiesen an {person_name}')}",
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    return "\r\n".join(fold_line(line) for line in lines) + "\r\n"
