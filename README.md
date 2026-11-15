# 🐕 Gassi-Planung

Web-App zur fairen Verteilung der Gassi-Runden: Wer geht wann an welchem Tag?

Jeder Tag hat **drei Zeitfenster** (Morgens, Mittags, Abends). Jede Person vergibt
pro Zeitfenster eine **Priorität** – oder **blockiert** das Zeitfenster komplett, wenn sie zu
der Zeit nicht zu Hause ist. Die App berechnet daraus den **optimalen
Wochenplan** und stellt ihn als Tabelle dar.

## Funktionen

- 📅 Wochenansicht (Mo–So) mit drei Zeitfenstern pro Tag, beliebig vor/zurück blättern
- 🙋 Personenverwaltung mit Farben
- 🎚️ Prioritäten pro Person und Zeitfenster: **3** = gern · **2** = ok · **1** = nur wenn nötig · **🚫** = nicht zu Hause.
  Einträge gelten für den Wochentag in zukünftigen Wochen; die erste Änderung
  einer Woche friert deren Plan bis Sonntag ein. Neue Prioritäten gelten ab Montag.
- 🧮 Optimale Planberechnung per ILP (ganzzahlige Optimierung, CBC-Solver via PuLP):
  - Blockierungen sind harte Regeln
  - Einsatzverteilung wird zuerst ausgeglichen; Präferenzen entscheiden danach
  - Zeitfenster, für die **alle** blockiert haben, werden als „⚠️ frei“ markiert, statt einen Fehler auszulösen
- ⚡ Präferenzänderungen aktualisieren kommende Wochen; der aktive Wochenplan bleibt unverändert
- 🔐 Jeder Teilnehmer erstellt mit Gruppeneinladungscode ein eigenes Konto
  mit Passwort und pflegt nur die eigenen Prioritäten.
- 📅 Persönlicher iCal-Abo-Link pro Teilnehmer für Apple Kalender und andere
  Kalender-Apps. Bei aktiven Erinnerungen enthält das Kalenderabo einen Alarm
  15 Minuten vor dem Termin; Planänderungen werden nicht als Benachrichtigung zugestellt.
- 🏅 Punkte und Abzeichen: Abgeschlossene Gassirunden bringen je einen Punkt.
  Daraus werden Stufen und Abzeichen für die Gruppe berechnet. Die
  Stufenschwellen steigen schrittweise (10, 25, 45, 70, … Punkte). Runden können
  nur im jeweiligen Zeitfenster mit 30 Minuten Toleranz gestartet werden;
  manuelle Runden startest du über „Jetzt Gassi gehen“ und „Gassi-Runde beenden“.
- Installierbare Web-App (PWA): Unter iOS lässt sich die App in Safari zum
  Home-Bildschirm hinzufügen, unter Android in Chrome installieren. Auf
  Smartphones bleibt die Schaltfläche zum Starten und Beenden einer Runde fest
  positioniert und lässt sich gut per Fingertipp bedienen; in der Web-PWA sind
  GPS-Ortung und Aufzeichnung ohne Internetverbindung nicht enthalten.
- 🐾 Übernahme und gemeinsame Runden: Eine andere Person kann eine geplante Runde
  mit Zustimmung übernehmen. Gemeinsam erfasste Runden zählen für jede beteiligte
  Person und schalten gemeinsame Runden- sowie Gruppengrößen-Abzeichen frei.
- 🐕 Hundepflegeprofile mit Fütterung, Medikamenten, Allergien, Tierarztkontakt
  und Gassi-Hinweisen. Für Abschlüsse werden Hunde pro Person ausgewählt und
  Kompatibilität wird geprüft; Gäste sehen die Pflegeinfos über einen separaten,
  widerrufbaren Nur-Lese-Link.
- 👤 Profilreiter mit lokal hochladbarem Profilbild, Stufe, Abzeichenkatalog, saisonalem
  Rückblick und persönlichen Anzeige-/Erinnerungseinstellungen. Saisonabzeichen
  werden bis sechs Monate im Voraus gezeigt; noch nicht erreichte Abzeichen sind
  in Graustufen mit eigens gezeichneten, jahresspezifischen SVG-Siegeln dargestellt.
  Externe Profilbilddienste werden nicht kontaktiert. Die Erinnerungseinstellung
  steuert iCal-Alarme und Browserbenachrichtigungen; die separate Einstellung für
  Mitteilungen steuert Hinweise zu Übernahmeanfragen und Entscheidungen.
- 💾 Persistenz in SQLite (keine Einrichtung nötig)

## Schnellstart

```bash
brew install python@3.15
"$(brew --prefix python@3.15)/bin/python3.15" -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --host 0.0.0.0 --port 8585
```

Dann im Browser öffnen: <http://localhost:8585>

Der Datenbankpfad ist per Umgebungsvariable `GASSI_DB` konfigurierbar
(Standard: `./gassi.sqlite3`). Anmeldungen sind standardmäßig erforderlich.

## Native iOS-App direkt auf dem iPhone testen

Die native iOS-Begleit-App ist eine separate Anwendung und nicht mit der
installierbaren Web-App identisch. So installierst du eine Entwicklungsversion
direkt auf deinem eigenen iPhone:

1. Installiere die vollständige Xcode-Version auf einem Mac. Die Xcode Command
   Line Tools allein reichen nicht aus. Die App erfordert iOS 17 oder neuer.
2. Wechsle auf den App-Branch, solange PR #33 noch nicht in `main` übernommen
   wurde. Nach der Übernahme verwendest du stattdessen `main`. Öffne anschließend
   das Xcode-Projekt:

   ```bash
   git fetch origin
   git switch --track origin/feat/8-ios-walk-distance
   open ios/GassiPlanung/GassiPlanung.xcodeproj
   ```

   Falls der Branch bereits in `main` übernommen wurde, verwende stattdessen:

   ```bash
   git switch main
   git pull --ff-only
   open ios/GassiPlanung/GassiPlanung.xcodeproj
   ```

3. Verbinde dein iPhone mit dem Mac und entsperre es. Wähle in Xcode das Projekt
   `GassiPlanung` und dessen App-Ziel aus. Öffne **Signing & Capabilities**,
   aktiviere die automatische Signierung und wähle dein **Personal Team**
   (persönliches Team) aus. Falls dein Apple-Konto noch nicht angezeigt wird,
   füge es unter **Xcode → Settings → Accounts** hinzu.
4. Wähle dein iPhone als Zielgerät und starte die App mit **Product → Run**
   (⌘R). Falls du dazu aufgefordert wirst, aktiviere den **Entwicklermodus**
   auf dem iPhone unter **Einstellungen → Datenschutz & Sicherheit →
   Entwicklermodus**, starte das Gerät neu und bestätige die Aktivierung.
   Bestätige bei Bedarf das Entwicklerprofil unter **Einstellungen → Allgemein →
   VPN und Geräteverwaltung**.
5. Öffne die App, gib die HTTPS-Adresse deines Gassi-Planung-Servers ein und
   melde dich mit deinem bestehenden Konto an. Erlaube den Standortzugriff
   **Immer**; ohne diese Berechtigung kann die App keine Runde starten. Sperre
   während eines Testrundgangs den Bildschirm, um die Hintergrundmessung zu
   überprüfen.

So wird eine Entwicklungsversion ausschließlich auf dem ausgewählten Gerät
installiert; es handelt sich nicht um eine TestFlight- oder App-Store-Version.
Ein Personal Team genügt zum Testen auf dem eigenen Gerät. Für eine Verteilung
an weitere Personen ist ein Apple-Developer-Team und beispielsweise TestFlight
erforderlich.

## Docker-Veröffentlichung

`compose.yaml` veröffentlicht die App nicht direkt. Sie hängt sich in das
bestehende Docker-Netz `traefik_proxy`; Traefik leitet
`gassiplan.verboese.de` über den Einstiegspunkt `websecure` an die App weiter und
verwendet den vorhandenen ACME-Resolver `myresolver`. Teleport bleibt für die
Serververwaltung; der öffentliche Datenverkehr der Anwendung läuft über Traefik, nicht
über Teleport.

Da in der vorhandenen Traefik-Konfiguration der Docker-Anbieter deaktiviert
ist, muss der Router aus [`deploy/traefik-gassi.yaml`](./deploy/traefik-gassi.yaml)
in die bestehende `traefik/traefik.yaml` unter `http:` übernommen werden. Den
vorhandenen `tls:`-Abschnitt dabei beibehalten. Die Datei wird über den
aktivierten Dateianbieter geladen.

Vor dem Start `.env.example` nach `.env` kopieren und `GASSI_SESSION_SECRET`
und `GASSI_INVITE_CODE` durch zufällige Geheimnisse ersetzen (z. B. mit
`openssl rand -hex 32`). `GASSI_SESSION_SECRET` dauerhaft behalten; den
Einladungscode an die Teilnehmer weitergeben. `.env` wird weder ins Containerabbild
kopiert noch von Git erfasst.

Für Benachrichtigungen im Browser zusätzlich ein VAPID-Schlüsselpaar erzeugen. Im Projektverzeichnis:

```bash
PROJECT_DIR="$PWD"
KEY_DIR="$HOME/.config/gassi-planung/vapid"
mkdir -p "$KEY_DIR"
cd "$KEY_DIR"
"$PROJECT_DIR/.venv/bin/vapid" --gen --applicationServerKey
base64 < private_key.pem | tr -d '\n'
```

Den von `vapid` ausgegebenen öffentlichen Anwendungsschlüssel (`Application Server Key`) in `GASSI_VAPID_PUBLIC_KEY`, die
Base64-Zeile in `GASSI_VAPID_PRIVATE_KEY_B64` und eine gültige Kontaktadresse in
`GASSI_VAPID_SUBJECT` eintragen. Das Schlüsselpaar dauerhaft behalten und die
private Base64-Zeile ausschließlich in `.env` oder als Geheimnis
speichern. Benachrichtigungen im Browser funktionieren nur über HTTPS.
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
- `GASSI_VAPID_PUBLIC_KEY`: öffentlicher, URL-sicher Base64-kodierter VAPID-Schlüssel
- `GASSI_VAPID_PRIVATE_KEY_B64`: private PEM-Datei, Base64-kodiert zur sicheren Geheimnisverwaltung
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
passwortlose Konten migriert; ein Administrator muss zuerst ein Passwort setzen. Für
einen frischen Start auf dem Server `GASSI_DB` auf eine neue Datenbankdatei
setzen; die bisherige Datenbank bleibt unangetastet.

Administratorrechte werden ausschließlich auf dem Server vergeben. Zuerst das
Konto in der Weboberfläche registrieren, dann das erste Administratorkonto per
Konsole bestimmen:

```bash
docker compose exec app python -m app.admin grant-admin "Jan"
docker compose exec app python -m app.admin list-users
```

Lokal ohne Docker: `.venv/bin/python -m app.admin grant-admin "Jan"`.
Weitere Befehle: `revoke-admin "Name"` und `reset-password "Name"`. Der letzte
Administrator kann nicht herabgestuft werden. Nach dem Anmelden sehen Administratoren die
Verwaltungsseite: Sie können Präferenzen anderer Teilnehmer für die Folgewoche
überschreiben und deren Passwort zurücksetzen. Ein Passwort-Reset beendet
vorhandene Sitzungen des betroffenen Kontos.

Die Aktivitätsliste zeigt erfolgreiche Anmeldungen und Präferenzänderungen
(einschließlich administrativer Überschreibungen) der letzten 90 Tage. Passwörter und
fehlgeschlagene Anmeldeversuche werden nicht protokolliert. Nach dieser Aktualisierung
müssen bestehende Sitzungen sich einmal neu anmelden.

### Teilnehmerkonto löschen

Es gibt keine Selbstbedienungs-Löschung. Bei aktivierter Anmeldung ist auch die
`DELETE /api/persons/{id}`-Route gesperrt. Ein Administrator mit Serverzugriff
kann das Konto in der SQLite-Datenbank entfernen. Dabei werden durch
Fremdschlüssel-Kaskaden auch die Prioritäten und den persönlichen Kalenderlink
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

### Datenbankmigration für Extra-Runden

Vor dem Upgrade auf Version `0.5.0` muss die SQLite-Datenbank gesichert werden; im
Docker-Betrieb kann dafür der obige `docker compose cp`-Befehl verwendet werden.
Die Migration beim App-Start erhält vorhandene Abschlüsse und führt sie als
geplante Runden weiter.

Sobald Extra-Runden gespeichert wurden, darf die Anwendung nicht auf eine Version
vor `0.5.0` zurückgerollt werden: ältere Versionen unterstützen Abschlüsse ohne
geplantes Zeitfenster nicht vollständig. Stattdessen einen Vorwärtsfix deployen oder die
Sicherung zurückspielen. Beim Wiederherstellen gehen alle seit der Sicherung
erfassten Extra-Runden verloren.

Das Kalenderabonnement liefert die Termine dieser Woche als einzelne Termine und lässt
die Termine ab nächster Woche nach den aktuellen Präferenzen wöchentlich
wiederkehren. So wirken Änderungen weder im aktuellen Wochenplan noch im
Kalender vor dem nächsten Montag.

Jeder Kalenderlink ist ein persönlicher geheimer Zugriffsschlüssel. Wer ihn kennt,
kann damit die persönlichen Kalenderdaten abrufen; „Link erneuern“ widerruft den alten Link. Der
Kalender-Knopf kopiert die URL. In Apple Kalender das Abonnement über
**Ablage → Neues Kalenderabo** mit dieser URL einrichten. Apple Kalender ruft
abonnierte Kalender selbstständig ab; den Aktualisierungszeitpunkt bestimmt Apple
Kalender. Bei aktivierten Erinnerungen enthält jeder Termin im Kalenderabonnement –
auch ein wöchentlich wiederkehrender – einen `VALARM` 15 Minuten vor `DTSTART`.
Bei deaktivierten Erinnerungen fehlt der Alarm. Kalender-Apps können Alarme in
Kalenderabonnements ignorieren oder erst beim nächsten Abruf aktualisieren.

## Wie der Plan berechnet wird

Für jede Kombination aus Tag × Zeitfenster × Person existiert eine binäre Variable
(„Person P geht an Tag D im Zeitfenster S“). Der Solver maximiert:

```
Σ Priorität(zugewiesenes Zeitfenster)  −  Fairnessgewicht × (max. Einsätze − min. Einsätze)  −  1000 × unbesetzte Zeitfenster
```

Das Standard-Fairnessgewicht beträgt `2 × Anzahl der Zeitfenster + 1`. Dadurch kann ein
Prioritätsunterschied die bestmögliche Verteilung nicht verschlechtern; bei
gleichmäßiger Verteilung entscheiden die Präferenzen.

Nebenbedingungen:

- Jedes Zeitfenster wird **genau einer Person** zugewiesen (oder bleibt als Notlösung unbesetzt)
- Blockierte Zeitfenster (🚫) sind für die Person **nicht zuweisbar**

Dadurch wird zuerst die Einsatzspanne minimiert. Erst unter gleich fairen
Verteilungen entscheiden die individuellen Präferenzen.

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```

## API (Auszug)

| Methode  | Pfad                                                     | Beschreibung                                                                                           |
| -------- | -------------------------------------------------------- | ------------------------------------------------------------------------------------------------------ |
| `GET`    | `/api/week?year=2026&week=42`                            | Woche inkl. Personen, Prioritäten und berechnetem Plan                                                 |
| `GET`    | `/api/plan?year=…&week=…`                                | Nur der berechnete Plan                                                                                |
| `POST`   | `/auth/register`                                         | Konto mit Einladungscode erstellen                                                                     |
| `POST`   | `/auth/login`                                            | Mit Name und Passwort anmelden                                                                         |
| `GET`    | `/api/persons`                                           | Teilnehmer der Gruppe auflisten (angemeldet)                                                           |
| `PUT`    | `/api/prefs`                                             | Eigene Priorität setzen: `weekday` (1=Mo…7=So), `slot`, `value` (`-1` blockiert, `1–3`, `null` löscht) |
| `GET`    | `/api/profile`                                           | Eigenes Profil, Stufe, letzte Aktivität und Einstellungen anzeigen                                     |
| `PATCH`  | `/api/profile/preferences`                               | Eigene Abzeichensichtbarkeit sowie Benachrichtigungs- und Erinnerungseinstellungen ändern              |
| `GET`    | `/api/push/public-key`                                   | Öffentlichen VAPID-Schlüssel für den eigenen Browser abrufen                                           |
| `POST`   | `/api/push/subscriptions`                                | Eigenes Abonnement für Browserbenachrichtigungen registrieren                                          |
| `DELETE` | `/api/push/subscriptions`                                | Eigenes Abonnement für Browserbenachrichtigungen entfernen                                             |
| `PUT`    | `/api/profile/avatar`                                    | Eigenes PNG/JPEG/WebP-Profilbild hochladen (maximal 2 MiB)                                             |
| `GET`    | `/api/profile/avatar`                                    | Eigenes Profilbild geschützt abrufen                                                                   |
| `DELETE` | `/api/profile/avatar`                                    | Eigenes Profilbild entfernen                                                                           |
| `GET`    | `/api/badges`                                            | Eigene Abzeichen, Kategorien und Fortschritt anzeigen; `?history=true` für vergangene Saisonabzeichen  |
| `GET`    | `/api/badges/{badge_id}`                                 | Abzeichenbedingung, Fortschritt und Teilnehmer anzeigen, die der Darstellung zugestimmt haben          |
| `GET`    | `/api/badges/{badge_id}/participants/{person_id}/avatar` | Profilbild eines für dieses Abzeichen sichtbaren Teilnehmers geschützt abrufen                         |
| `GET`    | `/api/gamification`                                      | Gruppenfortschritt, Abschlussstatus und eigene aktive Runde anzeigen                                   |
| `POST`   | `/api/walks/start`                                       | Geplante Gassirunde starten; `?walk_type=extra` startet eine Extra-Runde außerhalb des Plans            |
| `POST`   | `/api/walks/end`                                         | Aktive Gassirunde beenden und Abschluss speichern                                                       |
| `PUT`    | `/api/completions`                                       | Zugewiesene eigene Planrunde im aktuellen Zeitfenster abschließen                                      |
| `DELETE` | `/api/completions/{date}/{slot}`                         | Eigenen Abschluss entfernen                                                                            |
| `DELETE` | `/api/completions/{completion_id}`                       | Eigene Extra-Runde anhand ihrer Abschluss-ID entfernen                                                 |
| `GET`    | `/api/calendar/{token}.ics`                              | Persönliches iCal-Kalenderabonnement (Link ist widerrufbar)                                             |
| `POST`   | `/api/me/calendar-token`                                 | Persönlichen Kalender-Link erneuern                                                                    |

Profil-, Browserbenachrichtigungs- und Abzeichenendpunkte benötigen eine Anmeldung
und beziehen Profildaten nur für das eigene Konto. Profilbilder werden lokal als PNG,
JPEG oder WebP bis 2 MiB gespeichert; es gibt keine externen Profilbildabrufe.

`reminders_enabled` steuert iCal-`VALARM` und Browserbenachrichtigungen unabhängig von
`push_enabled`. Browserbenachrichtigungen benötigen zusätzlich eine Berechtigung und
ein im aktuellen Browser eingerichtetes Abonnement; ohne Berechtigung bleibt der
iCal-Alarm verfügbar. Unterstützt werden Benachrichtigungsdienste von Google FCM,
Mozilla und Apple. Browserbenachrichtigungen und Kalender-Apps können dieselbe
Erinnerung anzeigen; Kalender-Apps bestimmen selbst, wann sie das Abonnement
aktualisieren und ob sie `VALARM` unterstützen.

Der SQLite-Outbox-Dispatcher läuft im einzelnen FastAPI-Prozess und prüft fällige
Erinnerungen alle 30 Sekunden. Temporäre Fehler werden höchstens dreimal versucht
(30 und 60 Sekunden Abstand); ungültige Abos für Browserbenachrichtigungen
werden bei HTTP 404/410 entfernt.
Aufgaben nach Beginn des Zeitfensters verfallen. Nach einem Neustart werden fällige Aufgaben
nur noch vor Beginn des Zeitfensters versendet. Mehrere Instanzen der Anwendung werden derzeit
nicht unterstützt.

Der Abzeichenkatalog enthält aktuelle zählbasierte Abzeichen und historische Erfolge.
Abgelaufene Saisonabzeichen erscheinen mit `?history=true` im Rückblick. Neue Saisonabzeichen
werden versioniert ergänzt, ohne Definitionen oder Freischaltungen vergangener Jahre
zu überschreiben. Teilnehmer erscheinen in Abzeichendetails nur, wenn sie der Anzeige
ausdrücklich zugestimmt haben.

Die Zeitfenster im Kalender (Morgens 6–8 Uhr, Mittags 13:30–15:30 Uhr,
Abends 20–22 Uhr, Europe/Berlin) sind als Konstante `SLOT_TIMES` in
`app/ical.py` definiert.

Interaktive API-Doku: `http://localhost:8585/docs`

## Autostart (systemd-Benutzerdienst)

Vor dem Start `.env.example` nach `.env` kopieren und konfigurieren; der
Der Benutzerdienst lädt diese Datei über `EnvironmentFile`.

```bash
mkdir -p ~/.config/systemd/user
cp deploy/gassi-planung.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now gassi-planung
```

## Verwendete Technologien

FastAPI · SQLite (Python-Standardbibliothek) · PuLP/CBC · natives JavaScript (ohne Build-Schritt)
