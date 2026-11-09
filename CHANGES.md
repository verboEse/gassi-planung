# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
The current app version is maintained in `app/__init__.py`.

## [0.5.0] - 2026-11-06

### Added

- Extra-Gassirunden außerhalb der drei geplanten Slots, ohne Punkte und mit einem geheimen Abzeichen ab zehn Runden.

## [0.4.0] - 2026-11-06

### Added

- Gassi-Hinweise der Hunde werden vor dem Start angezeigt; Hunde bleiben bis zum Beenden unzugeordnet.

## [0.3.0] - 2026-11-05

### Added

- Geheime Abzeichen für Tages- und Rundenserien sowie außerplanmäßige Runden.
- Serien zeigen aktuelle Folge und Bestwert; natürliche Unterbrechungen erhalten erreichte Erfolge.

### Changed

- Admin-Korrekturen berechnen Serienerfolge anhand der gültigen Abschlüsse neu.

## [0.2.0] - 2026-11-04

### Added

- Feedback-Link in der App zum direkten Einreichen von Verbesserungsvorschlägen auf GitHub.
- Getrennte Ansichten für Profil/Einstellungen und Abzeichen/Fortschritt; Avatar führt zum Profil, Level zu Abzeichen und Gassirunden.
- Profilbild kann im Profil geändert werden.

### Changed

- Plan ist die Standardansicht; die App-Tabs wurden entfernt.
- Ungelesene Neuigkeiten werden direkt nach Wiederherstellung der Sitzung geladen, auch nach einem Seiten-Reload.
- Admin-Konten können Neuigkeiten ebenfalls abrufen und als gelesen markieren; der Lesestatus bleibt pro Konto gespeichert.

## [0.1.0]

### Added

- Semantische Versionierung mit Startversion 0.1.0 und Neuigkeiten beim Login; gelesene Meldungen werden je Nutzer gespeichert.
- Gemeinsame Gassirunden und bestätigte Übernahmen.

### Changed

- Alle Boxen außer dem Kalender starten standardmäßig eingeklappt.

## History

- **2026-10-23** — Planberechnung ausgewogener bei den Zuweisungen gemacht.
- **2026-10-15** — Admin-Teilnehmerverwaltung ergänzt; Präferenzänderungen auf die Folgewoche verschoben und die wirksame Woche angezeigt.
- **2026-10-13** — Authentifizierung, Administration, automatische Planaktualisierung, sichere Kalender-URLs sowie Caddy-/Traefik-Deployment ergänzt; Kontolöschung dokumentiert und lokale Umgebungsdateien aus Git ausgeschlossen.
- **2026-10-12** — Gassi-Planung als FastAPI-/SQLite-/ILP-App gestartet; persönlicher iCal-Feed mit wiederkehrenden Terminen und wochentagsbasierten Prioritäten ergänzt; GPL-Lizenz hinzugefügt.
