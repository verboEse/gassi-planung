# Spec Delta

## Purpose

Der Profilbereich bündelt persönliche Fortschritte, Avatar, Level, Aktivität und Einstellungen an einem eigenen Ort und trennt diese Inhalte vom Wochenplan.

## ADDED Requirements

### Requirement: Profile hub shows personal content

Das System MUST einen eigenen Profilbereich mit persönlichem Avatar, Level, Level-Bezeichnung, letzter Aktivität und profilbezogenen Einstellungen anbieten.

#### Scenario: Participant opens profile

- **WHEN** ein angemeldeter Teilnehmer den Profilbereich öffnet
- **THEN** sieht er seine persönlichen Profildaten und nicht die editierbaren Einstellungen anderer Teilnehmer

### Requirement: Avatar can be managed

Das System MUST einem Teilnehmer erlauben, ein eigenes Profilbild hochzuladen, zu ersetzen und zu entfernen. Uploads MUST auf zulässige Bildtypen und eine begrenzte Dateigröße geprüft werden.

#### Scenario: Avatar upload

- **WHEN** ein Teilnehmer ein gültiges Bild hochlädt
- **THEN** wird dieses Bild als sein Avatar gespeichert und angezeigt

#### Scenario: Invalid avatar upload

- **WHEN** ein Teilnehmer eine nicht unterstützte oder zu große Datei hochlädt
- **THEN** wird der Upload abgelehnt und der bisherige Avatar bleibt unverändert

### Requirement: Profile images are served locally

Das System MUST Profilbilder ausschließlich aus lokal gespeicherten Uploads oder einem lokalen Platzhalter beziehen und DARF keine externen Bilddienste anfragen.

#### Scenario: No uploaded avatar

- **WHEN** ein Teilnehmer kein Profilbild hochgeladen hat
- **THEN** zeigt das System Initialen und Teilnehmerfarbe als lokalen Platzhalter an

### Requirement: Level is visible in the header

Das System MUST neben dem Avatar das aktuelle Level und eine stabile Level-Bezeichnung anzeigen. Ein Klick auf diese Anzeige MUST zur persönlichen Abzeichenübersicht führen.

#### Scenario: Header level navigation

- **WHEN** ein Teilnehmer die Level-Anzeige in der Kopfzeile anklickt
- **THEN** öffnet sich seine persönliche Abzeichenübersicht

### Requirement: Notification preferences are separate

Das System MUST Push-Mitteilungen und Erinnerungen als eigene Profileinstellungen speichern und getrennt ein- oder ausschaltbar machen. Die Einstellung DARF keine fremden Konten verändern.

#### Scenario: Reminder preference changes

- **WHEN** ein Teilnehmer Erinnerungen deaktiviert
- **THEN** wird nur seine Einstellung geändert und der neue Zustand wird beim nächsten Öffnen angezeigt
