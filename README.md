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
  Einträge gelten für den Wochentag in zukünftigen Wochen; die erste Änderung
  einer Woche friert deren Plan bis Sonntag ein. Neue Prioritäten gelten ab Montag.
- 🧮 Optimale Planberechnung per ILP (ganzzahlige Optimierung, CBC-Solver via PuLP):
  - Blockierungen sind harte Regeln
  - Maximale Gesamt-Priorität
  - Weiche Fairness: Einsätze werden über die Woche möglichst gleichmäßig verteilt
  - Slots, an denen **alle** blockiert haben, werden als „⚠️ frei“ markiert statt zu crashen
- ⚡ Präferenzänderungen aktualisieren kommende Wochen; der aktive Wochenplan bleibt unverändert
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

`compose.yaml` veröffentlicht die App nicht direkt. Sie hängt sich in das
bestehende Docker-Netz `traefik_proxy`; Traefik leitet
`gassiplan.verboese.de` über den EntryPoint `websecure` an die App weiter und
verwendet den vorhandenen ACME-Resolver `myresolver`. Teleport bleibt für die
Host-Administration; der öffentliche App-Traffic läuft über Traefik, nicht
über Teleport.

Da in der vorhandenen Traefik-Konfiguration der Docker-Provider deaktiviert
ist, muss der Router aus [`deploy/traefik-gassi.yaml`](./deploy/traefik-gassi.yaml)
in die bestehende `traefik/traefik.yaml` unter `http:` übernommen werden. Den
vorhandenen `tls:`-Abschnitt dabei beibehalten. Die Datei wird über den
aktivierten File-Provider geladen.

Vor dem Start `.env.example` nach `.env` kopieren und beide Werte durch
zufällige Geheimnisse ersetzen (jeweils z. B. mit `openssl rand -hex 32`
erzeugen). `GASSI_SESSION_SECRET` dauerhaft behalten; den Einladungscode an die
Teilnehmer weitergeben. `.env` wird weder ins Image kopiert noch von Git erfasst.
Der Container startet mit einer neuen, persistenten Docker-Datenbank; die lokale
SQLite-Datei bleibt unverändert. DNS für `gassiplan.verboese.de` muss auf den
Docker-Host zeigen.

```bash
docker compose up -d --build
docker compose logs -f app
docker compose down
```

`docker compose down` erhält das Datenvolume. `docker compose down -v` löscht
auch die Container-Datenbank. Passwort-Reset im Container:
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

### Teilnehmerkonto löschen

Es gibt keine Selbstbedienungs-Löschung. Bei aktivierter Anmeldung ist auch die
`DELETE /api/persons/{id}`-Route gesperrt. Ein Administrator mit Serverzugriff
kann das Konto in der SQLite-Datenbank entfernen. Dabei werden durch
Fremdschlüssel-Kaskaden auch die Prioritäten und der persönliche Kalender-Feed
gelöscht. Die Aktion ist endgültig.

Im Docker-Betrieb zuerst eine Sicherung erstellen und die exakte Schreibweise
des Benutzernamens prüfen:

```bash
docker compose cp app:/data/gassi.sqlite3 ./gassi-backup.sqlite3
docker compose exec app python -c 'import sqlite3; c=sqlite3.connect("/data/gassi.sqlite3"); print(c.execute("SELECT username FROM accounts").fetchall())'
```

Dann `Jan` durch den gewünschten Benutzernamen ersetzen:

```bash
docker compose exec app python -c 'import sqlite3; c=sqlite3.connect("/data/gassi.sqlite3"); c.execute("PRAGMA foreign_keys=ON"); c.execute("DELETE FROM persons WHERE id=(SELECT person_id FROM accounts WHERE username=?)", ("Jan",)); c.commit()'
```

Der Kalender-Feed liefert Termine dieser Woche als einzelne Events und lässt
die Termine ab nächster Woche nach den aktuellen Präferenzen wöchentlich
wiederkehren. So wirken Änderungen weder im aktuellen Wochenplan noch im
Kalender vor dem nächsten Montag.

Jeder Kalender-Link ist ein persönliches Bearer-Geheimnis. Wer ihn kennt, kann
den persönlichen Feed lesen; „Link erneuern“ widerruft den alten Link. Der
Kalender-Knopf kopiert die URL. In Apple Kalender das Abo über
**Ablage → Neues Kalenderabo** mit dieser URL einrichten. Apple Kalender ruft
abonnierte Feeds selbstständig ab; der Aktualisierungszeitpunkt wird von Apple
Kalender bestimmt.

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
