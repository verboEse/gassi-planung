# Spec Delta

## Purpose

Soziale Abzeichenfunktionen machen gemeinsame Erfolge sichtbar, respektieren Privatsphäre und bilden eine sichere Grundlage für spätere Freunde-, Community- und Teilen-Funktionen.

## ADDED Requirements

### Requirement: Achievement visibility is opt-in

Das System MUST die Sichtbarkeit eines Teilnehmers in Listen freigeschalteter Personen standardmäßig deaktivieren. Der Teilnehmer MUST diese Sichtbarkeit selbst aktivieren und widerrufen können.

#### Scenario: Visibility is private by default

- **WHEN** ein neues Konto ein Abzeichen freischaltet
- **THEN** erscheint sein Name nicht in der Liste anderer Teilnehmer

#### Scenario: Participant opts in

- **WHEN** ein Teilnehmer die Sichtbarkeit seiner Abzeichen aktiviert
- **THEN** darf sein Name bei den freigeschalteten Personen der jeweiligen Abzeichen erscheinen

### Requirement: Badge details show opted-in achievers

Die Detailansicht eines Abzeichens MUST eine Liste anderer Teilnehmer nur dann anzeigen, wenn diese Teilnehmer der Sichtbarkeit zugestimmt haben. Wenn ein sichtbarer Teilnehmer ein Profilbild hinterlegt hat, MUST dieses oberhalb seines Namens angezeigt werden; ohne Bild wird ein Initialen-Platzhalter angezeigt.

#### Scenario: Opted-in achievers are listed

- **WHEN** mehrere Teilnehmer dasselbe Abzeichen freigeschaltet und Sichtbarkeit aktiviert haben
- **THEN** zeigt die Detailansicht nur diese Teilnehmer an

#### Scenario: Opted-in achiever avatar is shown

- **WHEN** ein sichtbarer Teilnehmer ein Profilbild hochgeladen hat
- **THEN** wird sein Bild oberhalb seines Namens angezeigt; andernfalls erscheinen Initialen mit Teilnehmerfarbe

### Requirement: Visibility can be revoked

Das System MUST einen Widerruf sofort berücksichtigen und den Teilnehmer aus zukünftigen Listen entfernen, ohne das persönliche Abzeichen zu löschen.

#### Scenario: Participant revokes visibility

- **WHEN** ein Teilnehmer die Sichtbarkeit widerruft
- **THEN** bleibt sein Abzeichen persönlich erhalten, aber sein Name wird nicht mehr in Teilnehmerlisten angezeigt

### Requirement: Social actions respect profile boundaries

Freunde, Community-Inhalte, Teilen/Geschenke und Bewertungsfunktionen MUST als getrennte Profilbereiche behandelt werden und dürfen ohne die jeweils erforderliche Zustimmung oder Berechtigung keine persönlichen Daten veröffentlichen.

#### Scenario: Social feature is not authorized

- **WHEN** ein Teilnehmer eine soziale Funktion ohne erforderliche Zustimmung verwendet
- **THEN** wird keine persönliche Aktivität veröffentlicht und die Funktion erklärt die fehlende Berechtigung
