# Design

## Context

Die Anwendung ist ein FastAPI-Backend mit SQLite und einem statischen JavaScript-Frontend. Der aktuelle Profilzustand liegt überwiegend in `persons` und `accounts`; Gamification-Abschlüsse und bereits bekannte Badge-Auszeichnungen werden separat gespeichert. Die Oberfläche zeigt Plan, Präferenzen und Gamification derzeit in einer gemeinsamen App-Ansicht.

Die Anforderungen aus Proposal und Specs sind querschnittlich: Navigation, Profildaten, Bildspeicher, Badge-Definitionen, saisonale Versionierung, Datenschutz und bestehende Gamification-Berechnung müssen zusammenarbeiten. Die Motivation ist im Proposal beschrieben; dieses Design legt die technische Struktur fest.

## Goals / Non-Goals

**Goals:**

- Einen Profil-Tab und eine persönliche Abzeichen-Navigation ohne zusätzliches Frontend-Framework ergänzen.
- Avatar-Upload lokal und sicher unterstützen.
- Badge-Definitionen von Badge-Auszeichnungen trennen, damit Kategorien, Bedingungen, Fortschritt und Jahresvarianten datengetrieben werden.
- Aktuelle Zähl-Badges korrigierbar und historische Badges dauerhaft behandeln.
- Saisonale Definitionen versioniert ergänzen, ohne vergangene Definitionen oder Auszeichnungen zu überschreiben.
- Opt-in-Sichtbarkeit von Teilnehmern strikt von persönlicher Badge-Historie trennen.
- Bestehende Punkte-, Level- und Abschlussdaten weiterverwenden.

**Non-Goals:**

- Kein neues Frontend-Framework und keine externe Gamification-Plattform.
- Keine externen Avatar- oder Gravatar-Abrufe.
- Kein vollständiger Push-Notification-Dienst in dieser Änderung; zunächst werden nur Einstellungen gespeichert.
- Keine vollständige Freundes-/Chat-/Community-Plattform und kein Zahlungs- oder Geschenk-System.
- Keine automatische Bewertung alter Abschlüsse mit neuen saisonalen Regeln, sofern die jeweilige Badge-Definition dies nicht ausdrücklich vorsieht.

## Decisions

### 1. Profil als eigener Frontend-Bereich mit URL-Zustand

Die bestehende statische Oberfläche erhält eine kleine Tab-Navigation für `Plan` und `Profil`. Profil- und Badge-Ansichten werden über URL-Hash oder Query-Zustand navigierbar, damit Browser-Reload und Zurück-Navigation funktionieren. Die Level-Anzeige in der Kopfzeile öffnet direkt die eigene Badge-Übersicht.

**Alternative:** Separate HTML-Seiten oder ein SPA-Framework. Das würde für die vorhandene kleine Anwendung zusätzliche Build- und Deployment-Komplexität einführen.

### 2. Avatar als geschützter SQLite-Datensatz

Ein Avatar-Datensatz gehört zu genau einer Person und speichert Quelle, Medientyp, geprüfte Bilddaten und Änderungszeitpunkt. Erlaubt werden nur PNG, JPEG und WebP bis zu einer festen Maximalgröße; SVG und unbekannte Formate werden abgelehnt. Der Avatar wird über einen authentifizierten Endpoint ausgeliefert und nicht als frei erratbarer statischer Dateipfad veröffentlicht.

**Alternative:** Dateien im öffentlichen Static-Verzeichnis ablegen. Das würde Löschung, Zugriffsschutz und Backups erschweren.

### 3. Profilbilder bleiben lokal

Profilbilder werden nur vom Teilnehmer hochgeladen und in der bestehenden SQLite-Datenbank gespeichert. Ohne Upload zeigt die UI Initialen mit der bestehenden Teilnehmerfarbe. Es werden keine externen Avatar-Dienste aufgerufen.

**Alternative:** Gravatar oder direkte Remote-URLs. Diese würden personenbezogene Abrufdaten an Dritte übermitteln und sind deshalb nicht Teil dieses Designs.

### 4. Badge-Definitionen werden datengetrieben

Eine `badge_definitions`-Struktur beschreibt stabile ID, Kategorie, Titel, Beschreibung, individueller Vektor-Art-Key, Bedingungstyp, Zielwert, Saison/Event, Jahr, Gültigkeitszeitraum und Aufbewahrungspolitik. Das Frontend zeichnet daraus lokale SVG-Siegel mit originalen geometrischen Motiven; Saison-ID/Jahr beeinflussen Palette und Jahresprägung. Es werden keine Emoji- oder Drittanbieter-Bilder verwendet. `person_badges` bleibt die Auszeichnungshistorie und erhält eine Referenz auf die Definition. Der Fortschrittsdienst berechnet aktuelle Kandidaten aus Abschlüssen und synchronisiert nur Badges mit `current-count`-Politik; `historical`-Badges wie „Volle Woche“ bleiben nach dem Erreichen erhalten.

**Alternative:** Badge-Namen und Bedingungen ausschließlich in JavaScript oder einer einzelnen Python-Konstante pflegen. Das würde saisonale Varianten, lokalisierbare Texte und historische Definitionen unnötig eng an Releases koppeln.

### 5. Saisonale Abzeichen werden versioniert geseedet

Neue Saisonabzeichen werden als additive, versionierte Definitionen mit eigener ID und eigenem Jahr eingespielt. Ein neues Jahr darf die Definition des Vorjahres nicht aktualisieren. Der Rückblick filtert diese Definitionen nach abgelaufenem Zeitraum; Auszeichnungen und Nicht-Erreichungen bleiben unterscheidbar.

**Alternative:** Saisonabzeichen jedes Jahr aus einer einzigen wiederverwendeten Definition berechnen. Dadurch könnten sich historische Bedingungen und Anzeigen rückwirkend verändern.

### 6. Badge-Fortschritt und Detailseiten nutzen einen gemeinsamen Katalog

Die Übersicht gruppiert Definitionen nach den sechs Hauptkategorien und zählt `erreicht/verfügbar`. Die Detailansicht verwendet dieselbe Definition wie die Übersicht und zeigt Bedingung, aktuellen Wert, Zielwert, Status und bei saisonalen Badges Zeitraum/Jahr. Opt-in-Teilnehmer werden erst nach der persönlichen Anzeige des Badges aus der Sichtbarkeitseinstellung gelesen.

**Alternative:** Fortschritt und Bedingungen separat in jeder UI-Karte berechnen. Das würde zu abweichenden Zahlen zwischen Übersicht und Detailseite führen.

### 7. Sichtbarkeit ist personenbezogen und standardmäßig privat

Eine Einstellung auf Personenebene steuert, ob der Name in Badge-Detailseiten anderer Teilnehmer erscheinen darf. Der eigene Badge-Status und die eigene Historie bleiben unabhängig davon sichtbar. Widerruf filtert den Namen sofort aus Listen, löscht aber keine eigene Auszeichnung.

**Alternative:** Gruppenweite Sichtbarkeit als Standard. Das wäre für bestehende Teilnehmer überraschend und widerspricht dem Opt-in-Ziel.

### 8. Profilbezogene Einstellungen werden gespeichert, Zustellung bleibt getrennt

Push- und Erinnerungspräferenzen erhalten eigene persistente Felder oder eine kleine Schlüssel-Wert-Struktur pro Person. Die erste Ausbaustufe speichert und zeigt den Zustand; ein späterer Benachrichtigungsdienst liest diese Präferenzen. Freunde, Community, Teilen/Geschenke und Bewertungen erhalten getrennte Einstiegspunkte, damit spätere Funktionen nicht in die Badge-Logik eingebaut werden.

**Alternative:** Einstellungen erst gemeinsam mit der Zustelltechnik bauen. Das würde den Profilumbau unnötig von einem externen Push-System abhängig machen.

## Risks / Trade-offs

- **[Risk] Avatardaten vergrößern die SQLite-Datenbank** → harte Größenbegrenzung, ein Avatar pro Person und bestehende Datenbanksicherungen verwenden.
- **[Risk] Bilddateien können missbrauchte Inhalte oder Parserrisiken enthalten** → SVG ablehnen, Größen-/Magic-Byte-Prüfung, geschütztes Ausliefern und keine Ausführung als HTML.
- **[Risk] Avatar-Bilder können Datenbank und Antworten vergrößern** → Upload-Größenlimit, ein Bild pro Person und Bilddaten nicht in Profil-JSON einbetten.
- **[Risk] Saisonale Definitionen können nachträglich falsch geändert werden** → immutable IDs mit Jahr und additive Seeds; alte Definitionen nicht überschreiben.
- **[Risk] Korrekturen können aktuelle und historische Badges unterschiedlich behandeln** → Retention-Policy je Definition und Tests für beide Fälle.
- **[Risk] Ein großer Profilumfang überlädt die erste UI** → Profil in klar getrennte Bereiche teilen und nicht funktionsfähige soziale Aktionen sichtbar, aber getrennt als spätere Erweiterung behandeln.

## Migration Plan

1. Additive Tabellen/Felder für Avatar, Profilpräferenzen, Badge-Definitionen, Badge-Historie und Sichtbarkeit beim Datenbankstart anlegen.
2. Bestehende Badge-IDs als Definitionen mit passenden Kategorien und Retention-Policies seeden; vorhandene `person_badges`-Einträge erhalten ihre Historie.
3. Bestehende Gamification-Abschlüsse und Levelberechnung in den neuen Katalogdienst einlesen, ohne historische Abschlüsse zu verändern.
4. Profil-Tab und Badge-Katalog neben der bisherigen Planansicht ausrollen; bei Fehlern kann die alte Gamification-Box zunächst als Fallback bestehen bleiben.
5. Nach erfolgreicher Migration alte, doppelte Gamification-Darstellungen entfernen.
6. Rollback: Frontend auf die alte Navigation zurücksetzen und neue additive Tabellen unangetastet lassen; sie enthalten keine Änderungen an Plan, Präferenzen oder Konten.
