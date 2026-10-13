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
- 🔐 Jeder Teilnehmer erstellt mit Gruppeneinladungscode ein eigenes Konto
  mit Passwort und pflegt nur die eigenen Prioritäten.
- 📅 Persönlicher iCal-Abo-Link pro Teilnehmer für Apple Kalender und andere
  Kalender-Apps. Der Kalender aktualisiert sich beim nächsten Abruf durch die
  Kalender-App; Änderungen werden nicht als Push zugestellt.
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
(Default: `./gassi.sqlite3`). Anmeldungen sind standardmäßig erforderlich.

## Docker-Veröffentlichung

`compose.yaml` startet die App intern und Caddy als einzigen öffentlich
veröffentlichten Dienst. Caddy stellt automatisch HTTPS für
`gassiplan.verboese.de` bereit. Dafür müssen DNS auf den Docker-Host zeigen und
TCP-Port 80 sowie 443 von außen erreichbar sein. Die Teleport-Verbindung zu
`pam.dreyers.eu` bleibt für die Administration des Hosts; der öffentliche
App-Traffic läuft über Caddy, nicht über Teleport.

Vor dem Start `.env.example` nach `.env` kopieren und beide Werte durch
zufällige Geheimnisse ersetzen (jeweils z. B. mit `openssl rand -hex 32`
erzeugen). `GASSI_SESSION_SECRET` dauerhaft behalten; den Einladungscode an die
Teilnehmer weitergeben. `.env` wird weder ins Image kopiert noch von Git erfasst.
Der Container startet mit einer neuen, persistenten Docker-Datenbank; die lokale
SQLite-Datei bleibt unverändert.

```bash
docker compose up -d --build
docker compose logs -f
docker compose down
```

`docker compose down` erhält die Datenvolumes. `docker compose down -v` löscht
sie samt Datenbank und Caddy-Zertifikaten. Passwort-Reset im Container:
`docker compose exec app python -m app.admin reset-password "Teilnehmername"`.

### Konten einrichten

Für den öffentlichen Betrieb HTTPS verwenden. Diese Umgebungsvariablen setzen:

- `GASSI_BASE_URL`: öffentliche HTTPS-Basisadresse
- `GASSI_SESSION_SECRET`: dauerhaftes, zufälliges Geheimnis (mindestens 32 Bytes)
- `GASSI_INVITE_CODE`: gemeinsamer, zufälliger Code für neue Teilnehmer (mindestens 32 Zeichen)

Neue Konten brauchen ein Passwort mit mindestens 12 Zeichen. Passwörter werden
mit `scrypt` gehasht gespeichert. Es gibt keinen E-Mail-Dienst und daher keine
Selbstbedienungs-Wiederherstellung. Ein Server-Administrator setzt ein
vergessenes Passwort so zurück:

```bash
python -m app.admin reset-password "Teilnehmername"
```

Das Programm fragt das neue Passwort verdeckt ab. Alte Teilnehmer ohne Konto
werden nicht automatisch verknüpft. Bereits vorhandene Apple-Konten werden als
passwortlose Konten migriert; ein Admin muss zuerst ein Passwort setzen. Für
einen frischen Start auf dem Server `GASSI_DB` auf eine neue Datenbankdatei
setzen; die bisherige Datenbank bleibt unangetastet.

Jeder Kalender-Link ist ein persönliches Bearer-Geheimnis. Wer ihn kennt, kann
den persönlichen Feed lesen; „Link erneuern“ widerruft den alten Link. Der
Ein-Klick-Abo-Knopf benötigt HTTPS. Lokal über HTTP kopiert er die URL zum
manuellen Einrichten in Apple Kalender (**Ablage → Neues Kalenderabo**). Apple
Kalender ruft abonnierte Feeds selbstständig ab; der Aktualisierungszeitpunkt
wird von Apple Kalender bestimmt.

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
| `POST` | `/auth/register` | Konto mit Einladungscode erstellen |
| `POST` | `/auth/login` | Mit Name und Passwort anmelden |
| `GET` | `/api/persons` | Teilnehmer der Gruppe auflisten (angemeldet) |
| `PUT` | `/api/prefs` | Eigene Priorität setzen: `weekday` (1=Mo…7=So), `slot`, `value` (`-1` blockiert, `1–3`, `null` löscht) |
| `GET` | `/api/calendar/{token}.ics` | Persönlicher iCal-Feed (Abo-Link ist widerrufbar) |
| `POST` | `/api/me/calendar-token` | Persönlichen Kalender-Link erneuern |

Die Slot-Zeitfenster im Kalender (Morgens 6–8 Uhr, Mittags 13:30–15:30 Uhr,
Abends 20–22 Uhr, Europe/Berlin) sind als Konstante `SLOT_TIMES` in
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
