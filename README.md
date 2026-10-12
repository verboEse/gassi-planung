# 🐕 Gassi-Planung

Web-App zur fairen Verteilung der Gassi-Runden: Wer geht wann an welchem Tag?

Jeder Tag hat **drei Timeslots** (Morgens, Mittags, Abends). Jede Person vergibt
pro Slot eine **Priorität** – oder **blockiert** den Slot komplett, wenn sie zu
der Zeit nicht zu Hause ist. Die App berechnet daraus den **optimalen
Wochenplan** und stellt ihn als Tabelle dar.

## Features

- 📅 Wochenansicht (Mo–So) mit drei Slots pro Tag, beliebig vor/zurück blättern
- 🙋 Personenverwaltung mit Farben
- 🎚️ Prioritäten pro Person & Slot: **3** = gern · **2** = ok · **1** = nur wenn nötig · **🚫** = nicht zu Hause.
  **Allgemeingültig pro Wochentag** (Mo–So) – einmal einstellen, gilt für jede Woche
- 🧮 Optimale Planberechnung per ILP (ganzzahlige Optimierung, CBC-Solver via PuLP):
  - Blockierungen sind harte Regeln
  - Maximale Gesamt-Priorität
  - Weiche Fairness: Einsätze werden über die Woche möglichst gleichmäßig verteilt
  - Slots, an denen **alle** blockiert haben, werden als „⚠️ frei“ markiert statt zu crashen
- ⚡ Plan wird bei jeder Änderung live neu berechnet
- 📅 **iCal-Feed pro Person** (`/api/calendar/{id}.ics`): eigene Gassi-Termine im
  persönlichen Kalender abonnieren (Google Kalender, Apple Kalender, …).
  Da der Plan sich wöchentlich wiederholt, enthält der Feed pro Wochentag×Slot
  **ein wiederkehrendes Event** (`RRULE:FREQ=WEEKLY`, **ohne Enddatum**) –
  nach Planänderungen sehen Abonnenten automatisch den neuen Stand.
- 💾 Persistenz in SQLite (kein Setup nötig)

## Schnellstart

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8585
```

Dann im Browser öffnen: <http://localhost:8585>

Der Datenbankpfad ist per Umgebungsvariable `GASSI_DB` konfigurierbar
(Default: `./gassi.sqlite3`).

## Wie der Plan berechnet wird

Für jede Kombination aus Tag × Slot × Person existiert eine binäre Variable
(„Person P geht an Tag D im Slot S“). Der Solver maximiert:

```
Σ Priorität(zugewiesener Slot)  −  0,25 × (max. Einsätze − min. Einsätze)  −  1000 × unbesetzte Slots
```

Nebenbedingungen:

- Jeder Slot wird **genau einer Person** zugewiesen (oder bleibt als Notlösung unbesetzt)
- Blockierte Slots (🚫) sind für die Person **nicht zuweisbar**

Dadurch gewinnen echte Prioritätenunterschiede (z. B. 3 vs. 1) immer gegen die
Fairness, aber bei gleichen Präferenzen wird sauber balanciert.

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```

## API (Auszug)

| Methode | Pfad | Beschreibung |
|---|---|---|
| `GET` | `/api/week?year=2026&week=42` | Woche inkl. Personen, Prioritäten und berechnetem Plan |
| `GET` | `/api/plan?year=…&week=…` | Nur der berechnete Plan |
| `GET`/`POST` | `/api/persons` | Personen auflisten / anlegen |
| `DELETE` | `/api/persons/{id}` | Person löschen |
| `PUT` | `/api/prefs` | Priorität setzen: `weekday` (1=Mo…7=So), `slot`, `value` (`-1` blockiert, `1–3`, `null` löscht) |
| `GET` | `/api/calendar/{id}.ics` | iCal-Feed der Person (wöchentlich wiederkehrende Events, ohne Enddatum) |

Die Slot-Zeitfenster im Kalender (Morgens 6–8 Uhr, Mittags 12–14 Uhr,
Abends 18–20 Uhr, Europe/Berlin) sind als Konstante `SLOT_TIMES` in
`app/ical.py` definiert.

Interaktive API-Doku: `http://localhost:8585/docs`

## Autostart (systemd User-Service)

```bash
mkdir -p ~/.config/systemd/user
cp deploy/gassi-planung.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now gassi-planung
```

## Tech-Stack

FastAPI · SQLite (stdlib) · PuLP/CBC · Vanilla JS (kein Build-Step)
