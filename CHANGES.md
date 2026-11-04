# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
The current app version is maintained in `app/__init__.py`.

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
