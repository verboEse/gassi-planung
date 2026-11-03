# Proposal

## Why

Die aktuelle Gamification-Box vermischt Punktestand, Gruppenübersicht und Aktionen. Ein eigener Profilbereich soll persönliche Fortschritte, Abzeichen und Einstellungen klar trennen und die Gamification als langfristige Motivation mit Leveln, Kategorien, saisonalen Erfolgen und optionalen Community-Funktionen ausbauen.

## What Changes

- Einen eigenen Profil-Tab für persönliche Inhalte und Einstellungen einführen.
- In der Kopfzeile ein eigenes Profilbild und das aktuelle Level mit Bezeichnung anzeigen. Ein Klick auf das Profilbild öffnet den Avatar-Upload; ohne eigenes Bild dienen Initialen und Teilnehmerfarbe als Platzhalter.
- Beim Anklicken des Levels eine persönliche Abzeichen-Übersicht mit Kategorien und Fortschrittsbalken öffnen, z. B. `8/23` erreichte Abzeichen.
- Abzeichen in verständliche Kategorien gruppieren: **Start & Entdecken**, **Runden-Meilensteine**, **Serien & Gewohnheiten**, **Treue & Langzeit**, **Saison & Ereignisse** sowie **Community & Teilen**.
- Einen **Rückblick** als separate Archiv-/Filteransicht für vergangene saisonale Erfolge, Events und Jahresabzeichen führen; Saison und Jahr werden zusätzlich als Metadaten gespeichert.
- Eine Detailansicht pro Abzeichen mit Fortschritt, Bedingung und optionaler Liste freigeschalteter Teilnehmer vorsehen.
- Jährlich neue saisonale Abzeichen ergänzen und vergangene Erfolge im Rückblick behalten.
- Profilbezogene Bereiche für letzte Aktivität, Push-/Erinnerungseinstellungen, Freunde, Community-Inhalte, Teilen/Geschenke und Bewertungen vorsehen.
- Sichtbarkeit von Personen und Freischaltungslisten nur nach ausdrücklicher Zustimmung erlauben.
- Die bestehende Punkte-, Level- und Abschlusslogik als Datenbasis weiterverwenden, aber die bisherige Gamification-Box in den Profilfluss überführen.

## Capabilities

### New Capabilities

- `profile-hub`: Profil-Tab, Profilbild-Upload, Kopfzeilen-Level, persönliche Aktivität und profilbezogene Einstellungen.
- `badge-catalog`: Kategorisierte Abzeichenübersicht, Fortschritt, Level-Bezeichnungen und Abzeichen-Detailseiten.
- `seasonal-achievements`: Jährlich definierte saisonale Abzeichen und dauerhafter Rückblick auf vergangene Erfolge.
- `social-achievements`: Opt-in-Sichtbarkeit freigeschalteter Teilnehmer sowie spätere Freunde-, Community-, Teilen-/Geschenk- und Bewertungsfunktionen.

### Modified Capabilities

## Impact

- Neue Navigation und Frontend-Ansichten für Profil und Abzeichen.
- Avatar-Speicherung, Upload-Validierung und geschützte Bildauslieferung.
- Datenmodell und API für Level-Bezeichnungen, Badge-Kategorien, Bedingungen, Fortschritt, Saison-Jahr und Opt-in-Sichtbarkeit.
- Erweiterung der bestehenden Gamification-Daten um dauerhafte Badge-Definitionen und historische Freischaltungen.
- Einstellungen für Push-Mitteilungen und Erinnerungen; konkrete Zustellung kann anschließend separat umgesetzt werden.
- Der Avatar-Upload gehört zum Scope. Es gibt keine Gravatar-Integration und keine externen Bildabrufe.
