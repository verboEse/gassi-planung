# Spec Delta

## Purpose

Saisonale und jährliche Abzeichen ermöglichen zeitbezogene Aktionen, ohne vergangene Erfolge zu verlieren oder bestehende Badge-Definitionen nachträglich umzudeuten.

## ADDED Requirements

### Requirement: Seasonal badges carry a season and year

Jedes saisonale Abzeichen MUST neben seiner stabilen ID eine Saison- oder Event-Kennung und ein Jahr besitzen.

#### Scenario: Annual event is listed

- **WHEN** ein saisonales Abzeichen für Valentinstag 2026 veröffentlicht wird
- **THEN** wird es als eigenes, eindeutig datiertes Abzeichen angezeigt

### Requirement: New seasonal badges can be added independently

Das System MUST saisonale Abzeichen für wiederkehrende Ereignisse jedes vorbereiteten Jahres anbieten, ohne Definitionen oder Freischaltungen anderer Jahre zu überschreiben. Saisonale Abzeichen mit Startdatum in den nächsten sechs Monaten MUST im aktuellen Katalog erscheinen; weiter in der Zukunft liegende Abzeichen bleiben bis zum Beginn dieses Anzeigezeitraums verborgen.

#### Scenario: New year is published

- **WHEN** die Definition für ein saisonales Ereignis 2027 hinzugefügt wird
- **THEN** bleiben das Ereignis 2026 und seine Freischaltungen unverändert erhalten

#### Scenario: Seasonal badge enters the six-month window

- **WHEN** ein saisonales Abzeichen höchstens sechs Monate vor seinem Startdatum liegt
- **THEN** erscheint es im aktuellen Katalog, während weiter entfernte Saisonabzeichen verborgen bleiben

### Requirement: Seasonal history is archived

Das System MUST vergangene saisonale Abzeichen in einer separaten Rückblickansicht anzeigen und dabei erreichte sowie nicht erreichte vergangene Abzeichen unterscheiden.

#### Scenario: Participant opens history

- **WHEN** ein Teilnehmer den Rückblick öffnet
- **THEN** sieht er vergangene Saisonabzeichen mit Jahr, Status und gegebenenfalls Freischaltungsdatum

### Requirement: Seasonal details explain the event

Die Detailansicht eines saisonalen Abzeichens MUST Zeitraum, Event-Bezeichnung, Bedingung und Fortschritt anzeigen.

#### Scenario: Seasonal badge details

- **WHEN** ein Teilnehmer ein saisonales Abzeichen öffnet
- **THEN** sieht er den gültigen Zeitraum und die zugehörige Bedingung
