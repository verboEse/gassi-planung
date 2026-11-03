# Notification Delivery

## Purpose

Diese Capability stellt rechtzeitige Browser-Erinnerungen für geplante Gassirunden anhand der persönlichen Erinnerungseinstellung zu.

## Requirements

### Requirement: Calendar feeds include reminders for enabled entries

Wenn die persönliche Erinnerungseinstellung aktiv ist, MUST der persönliche iCal-Feed für jeden eigenen geplanten Gassirunden-Termin einen `VALARM` 15 Minuten vor `DTSTART` enthalten. Bei deaktivierter Einstellung DARF dieser Alarm nicht enthalten sein.

#### Scenario: Reminder is enabled in the calendar feed

- **WHEN** ein Teilnehmer Erinnerungen aktiviert hat und ein eigener Gassirunden-Termin im iCal-Feed erscheint
- **THEN** enthält der Termin einen Alarm 15 Minuten vor Beginn

#### Scenario: Reminder is disabled in the calendar feed

- **WHEN** ein Teilnehmer Erinnerungen deaktiviert
- **THEN** enthalten seine geplanten Gassirunden-Termine im iCal-Feed keinen Alarm

### Requirement: Walk reminders are delivered as browser push

Das System MUST eine Erinnerung als Browser-Push an den Teilnehmer zustellen, dem die geplante Gassirunde zugeordnet ist, sofern dessen Erinnerungseinstellung aktiv und Browser-Benachrichtigungen erlaubt sind.

#### Scenario: Eligible reminder is delivered

- **WHEN** 15 Minuten bis zum Timeslot eines eigenen geplanten Gassirunden-Eintrags verbleiben und Erinnerungen sowie Browser-Benachrichtigungen aktiviert sind
- **THEN** erhält der zugeordnete Teilnehmer einen Browser-Push für diesen Kalendereintrag

#### Scenario: Browser permission is denied

- **WHEN** Browser-Benachrichtigungen nicht erlaubt sind, aber die persönliche Erinnerungseinstellung aktiv ist
- **THEN** wird kein Browser-Push versendet und der Alarm im iCal-Feed bleibt verfügbar
