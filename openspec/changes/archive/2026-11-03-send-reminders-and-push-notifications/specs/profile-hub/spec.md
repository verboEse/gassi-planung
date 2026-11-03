# Spec Delta

## MODIFIED Requirements

### Requirement: Notification preferences are separate

Das System MUST Push-Mitteilungen und Erinnerungen als eigene Profileinstellungen speichern und getrennt ein- oder ausschaltbar machen. Die Einstellung DARF keine fremden Konten verändern. Die Erinnerungseinstellung MUST Erinnerungen in den eigenen Kalendereinträgen aktivieren oder deaktivieren und bleibt unabhängig von der allgemeinen Push-Einstellung.

#### Scenario: Reminder preference changes

- **WHEN** ein Teilnehmer Erinnerungen deaktiviert
- **THEN** wird nur seine Erinnerungseinstellung geändert, die allgemeine Push-Einstellung bleibt unverändert und der neue Zustand wird beim nächsten Öffnen angezeigt

#### Scenario: Reminder preference applies to own calendar entries

- **WHEN** ein Teilnehmer Erinnerungen aktiviert
- **THEN** werden Erinnerungen für seine eigenen Kalendereinträge aktiviert, ohne die allgemeine Push-Einstellung oder fremde Konten zu verändern
