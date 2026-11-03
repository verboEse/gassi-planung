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
  - Einsatzverteilung wird zuerst ausgeglichen; Präferenzen entscheiden danach
  - Slots, an denen **alle** blockiert haben, werden als „⚠️ frei“ markiert statt zu crashen
- ⚡ Präferenzänderungen aktualisieren kommende Wochen; der aktive Wochenplan bleibt unverändert
- 🔐 Jeder Teilnehmer erstellt mit Gruppeneinladungscode ein eigenes Konto
  mit Passwort und pflegt nur die eigenen Prioritäten.
- 📅 Persönlicher iCal-Abo-Link pro Teilnehmer für Apple Kalender und andere
  Kalender-Apps. Bei aktiven Erinnerungen enthält der Feed Kalenderalarme 15 Minuten
  vor dem Termin; Planänderungen werden nicht als Push zugestellt.
- 🏅 Gamification: Erledigte Gassirunden geben je einen Punkt; daraus werden
  Level und Badges für die Gruppe berechnet. Die Level-Schwellen steigen
  progressiv (10, 25, 45, 70, … Punkte). Runden werden nur im jeweiligen
  Zeitfenster mit 30 Minuten Toleranz gestartet; manuelle Runden laufen über
  „Jetzt Gassi gehen“ und „Gassi-Runde beenden“.
- 👤 Profil-Tab mit lokalem Avatar-Upload, Level, Abzeichenkatalog, saisonalem
  Rückblick und persönlichen Anzeige-/Erinnerungseinstellungen. Saisonabzeichen
  werden bis sechs Monate im Voraus gezeigt; noch nicht erreichte Abzeichen sind
  in Graustufen mit eigens gezeichneten, jahresspezifischen SVG-Siegeln dargestellt.
  Externe Avatar-Dienste werden nicht kontaktiert. Die Erinnerungseinstellung
  steuert iCal-Alarme und Browser-Push; allgemeine Push-Mitteilungen sind nicht Teil
  dieses Versands.
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

Vor dem Start `.env.example` nach `.env` kopieren und `GASSI_SESSION_SECRET`
und `GASSI_INVITE_CODE` durch zufällige Geheimnisse ersetzen (z. B. mit
`openssl rand -hex 32`). `GASSI_SESSION_SECRET` dauerhaft behalten; den
Einladungscode an die Teilnehmer weitergeben. `.env` wird weder ins Image
kopiert noch von Git erfasst.

Für Browser-Push zusätzlich ein VAPID-Schlüsselpaar erzeugen. Im Projekt-Root:

```bash
PROJECT_DIR="$PWD"
KEY_DIR="$HOME/.config/gassi-planung/vapid"
mkdir -p "$KEY_DIR"
cd "$KEY_DIR"
"$PROJECT_DIR/.venv/bin/vapid" --gen --applicationServerKey
base64 < private_key.pem | tr -d '\n'
```

Den ausgegebenen `Application Server Key` in `GASSI_VAPID_PUBLIC_KEY`, die
Base64-Zeile in `GASSI_VAPID_PRIVATE_KEY_B64` und eine gültige Kontaktadresse in
`GASSI_VAPID_SUBJECT` eintragen. Das Schlüsselpaar dauerhaft behalten und die
private Base64-Zeile ausschließlich in `.env` beziehungsweise einem Secret
speichern. Die App benötigt für Browser-Push HTTPS.
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
- `GASSI_VAPID_PUBLIC_KEY`: öffentlicher, URL-sicher Base64-kodierter Push-Schlüssel
- `GASSI_VAPID_PRIVATE_KEY_B64`: private PEM-Datei, Base64-kodiert für die Secret-Umgebung
- `GASSI_VAPID_SUBJECT`: Kontaktadresse im VAPID-Format, z. B. `mailto:admin@example.com`

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

Admin-Rechte werden ausschließlich auf dem Server vergeben. Erst das Konto im
Web-UI registrieren, dann das erste Admin-Konto per Konsole bestimmen:

```bash
docker compose exec app python -m app.admin grant-admin "Jan"
docker compose exec app python -m app.admin list-users
```

Lokal ohne Docker: `.venv/bin/python -m app.admin grant-admin "Jan"`.
Weitere Befehle: `revoke-admin "Name"` und `reset-password "Name"`. Der letzte
Admin kann nicht herabgestuft werden. Nach dem Anmelden sehen Admins die
Verwaltungsseite: Sie können Präferenzen anderer Teilnehmer für die Folgewoche
überschreiben und deren Passwort zurücksetzen. Ein Passwort-Reset beendet
vorhandene Sitzungen des betroffenen Kontos.

Die Aktivitätsliste zeigt erfolgreiche Anmeldungen und Präferenzänderungen
(einschließlich Admin-Overrides) der letzten 90 Tage. Passwörter und
fehlgeschlagene Anmeldeversuche werden nicht protokolliert. Nach diesem Update
müssen bestehende Sitzungen sich einmal neu anmelden.

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
Kalender bestimmt. Bei aktivierten Erinnerungen enthält jeder Termin im Feed –
auch ein wöchentlich wiederkehrender – einen `VALARM` 15 Minuten vor `DTSTART`.
Bei deaktivierten Erinnerungen fehlt der Alarm. Kalender-Apps können Alarme in
abonnierten Feeds ignorieren oder erst beim nächsten Feed-Abruf aktualisieren.

## Wie der Plan berechnet wird

Für jede Kombination aus Tag × Slot × Person existiert eine binäre Variable
(„Person P geht an Tag D im Slot S“). Der Solver maximiert:

```
Σ Priorität(zugewiesener Slot)  −  Fairnessgewicht × (max. Einsätze − min. Einsätze)  −  1000 × unbesetzte Slots
```

Das Standard-Fairnessgewicht beträgt `2 × Slotzahl + 1`. Dadurch kann ein
Prioritätsunterschied die bestmögliche Verteilung nicht verschlechtern; bei
gleichmäßiger Verteilung entscheiden die Präferenzen.

Nebenbedingungen:

- Jeder Slot wird **genau einer Person** zugewiesen (oder bleibt als Notlösung unbesetzt)
- Blockierte Slots (🚫) sind für die Person **nicht zuweisbar**

Dadurch wird zuerst die Einsatzspanne minimiert. Erst unter gleich fairen
Verteilungen entscheiden die individuellen Präferenzen.

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
| `GET` | `/api/profile` | Eigenes Profil, Level, letzte Aktivität und Einstellungen anzeigen |
| `PATCH` | `/api/profile/preferences` | Eigene Abzeichen-Sichtbarkeit und Push-/Erinnerungspräferenzen ändern |
| `GET` | `/api/push/public-key` | Öffentlichen VAPID-Schlüssel für den eigenen Browser abrufen |
| `POST` | `/api/push/subscriptions` | Eigenes Browser-Push-Abo registrieren |
| `DELETE` | `/api/push/subscriptions` | Eigenes Browser-Push-Abo entfernen |
| `PUT` | `/api/profile/avatar` | Eigenes PNG/JPEG/WebP-Profilbild hochladen (maximal 2 MiB) |
| `GET` | `/api/profile/avatar` | Eigenes Profilbild geschützt abrufen |
| `DELETE` | `/api/profile/avatar` | Eigenes Profilbild entfernen |
| `GET` | `/api/badges` | Eigene Abzeichen, Kategorien und Fortschritt anzeigen; `?history=true` für vergangene Saisonabzeichen |
| `GET` | `/api/badges/{badge_id}` | Abzeichenbedingung, Fortschritt und opt-in Teilnehmerliste anzeigen |
| `GET` | `/api/badges/{badge_id}/participants/{person_id}/avatar` | Profilbild eines für dieses Abzeichen sichtbaren Teilnehmers geschützt abrufen |
| `GET` | `/api/gamification` | Gruppenfortschritt, Abschlussstatus und eigene aktive Runde anzeigen |
| `POST` | `/api/walks/start` | Gassi-Session im aktuellen Zeitfenster starten |
| `POST` | `/api/walks/end` | Aktive Gassi-Session beenden und Abschluss speichern |
| `PUT` | `/api/completions` | Zugewiesene eigene Planrunde im aktuellen Zeitfenster abschließen |
| `DELETE` | `/api/completions/{date}/{slot}` | Eigenen Abschluss entfernen |
| `GET` | `/api/calendar/{token}.ics` | Persönlicher iCal-Feed (Abo-Link ist widerrufbar) |
| `POST` | `/api/me/calendar-token` | Persönlichen Kalender-Link erneuern |

Profil-, Push-Abo- und Badge-Endpunkte benötigen eine Anmeldung und beziehen
Profildaten nur für das eigene Konto. Avatarbilder werden lokal als PNG, JPEG oder
WebP bis 2 MiB gespeichert; es gibt keine externen Avatar-Abrufe.

`reminders_enabled` steuert iCal-`VALARM` und Browser-Push unabhängig von
`push_enabled`. Browser-Push benötigt zusätzlich die Berechtigung und ein Abo des
aktuellen Browsers; ohne Berechtigung bleibt der iCal-Alarm verfügbar. Unterstützt
werden Push-Endpunkte von Google FCM, Mozilla und Apple. Browser-Push und Kalender-
App können dieselbe Erinnerung anzeigen; Kalender-Clients bestimmen selbst, wann sie
den Feed aktualisieren und ob sie `VALARM` unterstützen.

Der SQLite-Outbox-Dispatcher läuft im einzelnen FastAPI-Prozess und prüft fällige
Erinnerungen alle 30 Sekunden. Temporäre Fehler werden höchstens dreimal versucht
(30 und 60 Sekunden Abstand); ungültige Push-Abos werden bei HTTP 404/410 entfernt.
Jobs nach Beginn des Timeslots verfallen. Nach einem Neustart werden fällige Jobs
nur noch vor Beginn des Timeslots versendet. Mehrere App-Instanzen werden derzeit
nicht unterstützt.

Der Badge-Katalog enthält aktuelle Zähl-Badges und historische Erfolge. Abgelaufene
Saisonabzeichen erscheinen mit `?history=true` im Rückblick. Neue Saisonabzeichen
werden versioniert ergänzt, ohne Definitionen oder Freischaltungen vergangener Jahre
zu überschreiben. Teilnehmer erscheinen in Badge-Details nur nach eigenem Opt-in.

Die Slot-Zeitfenster im Kalender (Morgens 6–8 Uhr, Mittags 13:30–15:30 Uhr,
Abends 20–22 Uhr, Europe/Berlin) sind als Konstante `SLOT_TIMES` in
`app/ical.py` definiert.

Interaktive API-Doku: `http://localhost:8585/docs`

## Autostart (systemd User-Service)

Vor dem Start `.env.example` nach `.env` kopieren und konfigurieren; der
User-Service lädt diese Datei über `EnvironmentFile`.

```bash
mkdir -p ~/.config/systemd/user
cp deploy/gassi-planung.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now gassi-planung
```

## Tech-Stack

FastAPI · SQLite (stdlib) · PuLP/CBC · Vanilla JS (kein Build-Step)
