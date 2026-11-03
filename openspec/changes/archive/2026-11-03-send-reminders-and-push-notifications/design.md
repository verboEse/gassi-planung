# Design

## Context

Siehe [proposal.md](./proposal.md). Die Anwendung besteht aus einem FastAPI-Backend, SQLite und einer Vanilla-JavaScript-Oberfläche. Der persönliche iCal-Feed wird in `app/ical.py` erzeugt; seine Timeslots sind in `Europe/Berlin` definiert. Das Deployment betreibt derzeit einen App-Prozess mit persistenter SQLite-Datenbank.

## Goals / Non-Goals

**Goals:**
- Für aktive Erinnerungseinstellungen sowohl Browser-Push als auch iCal-Alarme 15 Minuten vor dem jeweiligen Gassirunden-Timeslot auslösen.
- Zustellung an das Konto und die Kalendertermine des zuständigen Teilnehmers binden.
- Erinnerungen bei deaktivierter Präferenz unterdrücken; die allgemeine Push-Einstellung bleibt unabhängig.

**Non-Goals:**
- Push-Mitteilungen bei Änderungen am Gassiplan, E-Mail oder native App-Benachrichtigungen.
- Eine vom Teilnehmer konfigurierbare Erinnerungszeit.

## Decisions

### iCal-Alarme werden im bestehenden Feed ausgegeben

`build_ics` erhält den Erinnerungsstatus der Feed-Person. Bei aktiven Erinnerungen ergänzt der Generator jedes einzelne und wiederkehrende `VEVENT` um `ACTION:DISPLAY` und `TRIGGER:-PT15M`; andernfalls enthält es kein `VALARM`. Die Einstellung wird beim Abruf des persönlichen Feeds erneut gelesen, damit Änderungen beim nächsten Client-Abruf wirksam werden. `Europe/Berlin` bleibt die Quelle der Slot-Zeiten; der relative Alarm folgt dem jeweiligen `DTSTART` und damit auch Sommer-/Winterzeit.

Das ist der passende Zustellweg für native Kalenderalarme. Ein reiner Browser-Hinweis im Wochenplan würde Kalender-Apps nicht erreichen. Kalender-Clients bestimmen selbst, wann sie abonnierte Feeds aktualisieren und ob sie Alarme daraus anzeigen.

### Browser-Push nutzt Web Push und registrierte Browser-Abos

Die Oberfläche fordert die Browser-Berechtigung erst nach einer bewussten Aktivierung an, registriert einen root-scoped Service Worker und sendet dessen Push-Abo über einen authentifizierten API-Endpunkt. Das Backend speichert mehrere Abos pro Teilnehmer; Entfernen eines Abos ist ebenfalls authentifiziert. Der Service Worker zeigt eingehende Erinnerungen an.

Der Server versendet nach Web Push mit VAPID. VAPID-Schlüssel kommen aus Deployment-Secrets; der öffentliche Schlüssel wird der Oberfläche bereitgestellt. Eine etablierte Python-Web-Push-Bibliothek übernimmt Payload-Verschlüsselung und Protokollsignierung, statt Kryptografie selbst zu implementieren. Browser-Push ist HTTPS-gebunden. Ohne erteilte Browser-Berechtigung entfällt dieser Zustellweg, nicht aber der iCal-Alarm.

`reminders_enabled` steuert Erinnerungen unabhängig von `push_enabled`; Planänderungen werden in diesem Change nicht gepusht. Abgelaufene Browser-Abos (HTTP 404/410) werden entfernt, temporäre Fehler erneut versucht.

### Ein SQLite-Outbox-Worker plant und versendet Erinnerungen

Ein dauerhafter Outbox-Eintrag pro Teilnehmer, Datum und Timeslot speichert den UTC-Fälligkeitszeitpunkt, Zustellstatus und Versuchszähler. Ein Reconciler leitet geplante Einträge aus derselben Planberechnung wie der Kalender-Feed ab und aktualisiert ausstehende Jobs, wenn sich der Plan ändert. Vor dem Versand prüft der Worker erneut, dass die Runde noch zugewiesen und `reminders_enabled` aktiv ist. Jobs nach Beginn des Timeslots werden verworfen statt verspätet zugestellt.

Ein einzelner asynchroner Worker im FastAPI-Lifespan prüft die Outbox regelmäßig; SQLite bleibt die persistente Quelle und ein zusätzlicher Scheduler-Dienst ist für das aktuelle Einzelprozess-Deployment nicht nötig. Eindeutige Schlüssel und transaktionales Beanspruchen verhindern doppelte Jobs. Bei mehreren App-Instanzen muss der Versand in einen einzelnen Worker verlagert oder um eine verteilte Claim-Strategie ergänzt werden.

Die Fälligkeit wird als lokale Slot-Startzeit minus 15 Minuten in `Europe/Berlin` berechnet und anschließend als UTC gespeichert. So bleibt die Planung bei Zeitumstellungen konsistent.

### Daten und Zugriff bleiben kontobezogen

Eine SQLite-Migration ergänzt Tabellen für Browser-Abos und die Reminder-Outbox, jeweils mit Fremdschlüssel zum Teilnehmer und Löschkaskade. Abo-Endpunkte verwenden das angemeldete eigene Konto; ein Teilnehmer kann keine Abos anderer Konten registrieren oder entfernen. Push-Endpunkte, Schlüsselmaterial und vollständige Payloads werden nicht protokolliert. Die Benachrichtigung enthält nur die für die eigene Gassirunde nötigen Angaben.

## Risks / Trade-offs

- **Kalender-Clients aktualisieren abonnierte Feeds verzögert oder ignorieren `VALARM`** → Browser-Push ist der zweite Zustellweg; das tatsächliche Aktualisierungsintervall des Clients ist nicht steuerbar.
- **Browser-Push und Kalender-App können dieselbe Erinnerung doppelt anzeigen** → Beide Wege bleiben gemäß Anforderung aktiv; dieselbe Kennung als Web-Push-Tag ersetzt versehentliche Wiederholungen im Browser.
- **Push-Abo oder Berechtigung wird entzogen** → Der Worker entfernt dauerhaft ungültige Abos; der iCal-Alarm bleibt unabhängig verfügbar.
- **App ist zur Fälligkeit nicht erreichbar** → Ausstehende Jobs werden beim Neustart nur vor Beginn des Timeslots versendet; danach verfallen sie.
- **Mehrere Worker könnten gleichzeitig versenden** → Das aktuelle Deployment bleibt auf einen App-Prozess begrenzt; vor horizontaler Skalierung wird ein dedizierter Worker oder eine robuste Claim-Strategie benötigt.

## Migration Plan

1. SQLite-Migration für Browser-Abos und Outbox ergänzen; bestehende Präferenzen bleiben unverändert und standardmäßig deaktiviert.
2. VAPID-Schlüsselpaar als Deployment-Secret konfigurieren und den öffentlichen Schlüssel bereitstellen; private Schlüssel nicht in Repository oder Logs ablegen.
3. Root-scoped Service Worker, Abo-Endpunkte, Dispatcher und bedingte iCal-`VALARM`-Ausgabe gemeinsam ausrollen.
4. Bei Rollback den Dispatcher deaktivieren und Abos/Outbox unangetastet lassen; der Kalender-Feed kann ohne `VALARM` weiter ausgeliefert werden.
