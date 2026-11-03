# Tasks

## 1. Datenmodell und Migration

- [x] 1.1 Profilfelder und Profilpräferenzen für Avatar-Daten, Badge-Sichtbarkeit sowie Push-/Erinnerungseinstellungen ergänzen; Migration auf frischer und bestehender SQLite-Datenbank verifizieren.
- [x] 1.2 `badge_definitions` mit stabiler ID, Kategorie, Beschreibung, individuellem Vektor-Art-Key, Bedingung, Zielwert, Saison, Jahr, Zeitraum und Retention-Policy ergänzen; Schema- und Seed-Test für Kategorien und Art-Keys verifizieren.
- [x] 1.3 Bestehende Badge-Auszeichnungen in das Definitionsmodell überführen und aktuelle Zähl-Badges von historischen Badges unterscheiden; Migration mit vorhandenen `person_badges`-Einträgen verifizieren.
- [x] 1.4 Level-Bezeichnungen und lokalisierbare Texte als versionierbare Daten ergänzen; Test für Levelnummer, Bezeichnung und die bestehenden progressiven Schwellen verifizieren.

## 2. Profil- und Badge-Backend

- [x] 2.1 Authentifizierte Profil-API für eigene Profildaten, Avatarstatus, Level, letzte Aktivität und Präferenzen bereitstellen; API-Tests müssen fremden Zugriff ablehnen.
- [x] 2.2 Avatar-Upload, Ersetzen, Entfernen und geschütztes Ausliefern mit PNG/JPEG/WebP- und Größenprüfung implementieren; API-Tests für gültige, ungültige und fremde Uploads verifizieren.
- [x] 2.3 Gravatar-Integration aus Datenschutzgründen aus dem Scope nehmen; Spezifikation und Implementierung dürfen keine externen Bildabrufe auslösen.
- [x] 2.4 Badge-Katalog-API für Kategorien, `erreicht/verfügbar`, Fortschrittswerte, Detaildaten und Retention-Status implementieren; API-Tests für aktuelle Zähl-Badges und historische Badges verifizieren.
- [x] 2.5 Zehn jährliche Saison-Events für fünf Jahre mit Jahr, Zeitraum und Rückblickstatus bereitstellen; aktuellen Katalog auf sechs Monate begrenzen und per API-Test für 2026/2027 verifizieren.
- [x] 2.6 Opt-in-Sichtbarkeit und Liste freigeschalteter Teilnehmer implementieren; API-Tests für Standard-Privatheit, Zustimmung und sofortigen Widerruf verifizieren.
- [x] 2.7 Push- und Erinnerungspräferenzen als getrennte eigene Einstellungen implementieren; API-Tests für unabhängiges Speichern und Schutz fremder Konten verifizieren.

## 3. Frontend-Navigation und Profil

- [x] 3.1 Tab-Navigation für Plan und Profil mit URL-/Reload-Zustand ergänzen; Browserprüfung muss zwischen beiden Ansichten navigieren und den Zustand nach Reload erhalten.
- [x] 3.2 Kopfzeile um Avatar, Levelnummer und Level-Bezeichnung ergänzen; Browserprüfung muss Klick auf Level zur persönlichen Badge-Übersicht und Klick auf Avatar zum Upload führen.
- [x] 3.3 Profilbereich mit letzter Aktivität, lokalem Avatar-Upload sowie Push-/Erinnerungspräferenzen umsetzen; Browserprüfung muss Änderungen nur für das eigene Konto speichern.
- [x] 3.4 Badge-Übersicht nur mit befüllten Kategorien, individuell gezeichneten und jahresspezifischen SVG-Siegeln, erreicht/verfügbar-Zähler und Fortschrittsbalken umsetzen; bei Stufen-Badges Fortschritt anzeigen, bei Einmal-Badges Zähler ausblenden und Saisonabzeichen auf sechs Monate voraus begrenzen; Browserprüfung verifizieren.
- [x] 3.5 Badge-Detailseite mit eigenem jahresspezifischem SVG-Siegel, Bedingung, optionalem Fortschritt und Saison-/Jahresdaten umsetzen; opt-in Teilnehmerliste zeigt Avatar über Namen oder Initialen-Platzhalter und entfernt beides sofort bei Widerruf.
- [x] 3.6 Rückblickansicht für vergangene Saisonabzeichen und getrennte Einstiegspunkte für Freunde, Community, Teilen/Geschenke und Bewertungen ergänzen; Browserprüfung muss vergangene Jahresdefinitionen getrennt anzeigen und nicht autorisierte soziale Aktionen blockieren.

## 4. Dokumentation und Integration

- [x] 4.1 README/API-Dokumentation um Profil-, Avatar-, Badge-, Saison- und Sichtbarkeitsregeln ergänzen; dokumentierte Endpunkte gegen die OpenAPI-Doku prüfen.
- [x] 4.2 Bestehende Gamification-, Auth-, Datenbank- und Kalender-Tests mit Profil-/Badge-Fällen ergänzen; gezielte Tests pro Backend-Gruppe müssen erfolgreich sein.
- [x] 4.3 Vollständige Testsuite, JavaScript-Syntaxprüfung, `git diff --check` und `openspec validate redesign-gamification-profile --strict` ausführen; alle Prüfungen müssen erfolgreich sein.

## Workflow follow-up

- Nach abgeschlossenem Review den Change archivieren und die archivierten Specs erneut validieren.
