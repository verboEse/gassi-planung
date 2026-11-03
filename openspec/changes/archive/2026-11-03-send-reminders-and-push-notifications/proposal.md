# Proposal

## Why

Push-Mitteilungen und Erinnerungen werden aktuell nur als Profileinstellungen gespeichert und nicht versendet. Dadurch können Teilnehmende sich nicht auf die aktivierten Benachrichtigungen verlassen.

## What Changes

- Push-Mitteilungen und Erinnerungen tatsächlich zustellen, statt nur die zugehörigen Präferenzen zu speichern.
- Die bestehenden, getrennten Profilpräferenzen als Grundlage dafür verwenden, ob die jeweilige Benachrichtigungsart versendet werden darf.
- Auslöser, Versandzeitpunkte, unterstützte Kanäle und erforderliche Berechtigungs- oder Abonnementabläufe in den Spezifikationen und im Design festlegen.

## Capabilities

### New Capabilities
- `notification-delivery`: Benachrichtigungen und Erinnerungen anhand relevanter Auslöser und persönlicher Präferenzen zustellen.

### Modified Capabilities
- `profile-hub`: Die bestehenden Push- und Erinnerungseinstellungen steuern künftig die tatsächliche Zustellung und bleiben voneinander getrennt.

## Impact

Betroffen sind die Profilpräferenzen und ihre API, der Benachrichtigungsversand und dessen Auslöser, die Oberfläche für gegebenenfalls erforderliche Berechtigungen sowie Dokumentation und Tests. Konkrete Transport- und Planungsmechanismen werden im Design festgelegt.
