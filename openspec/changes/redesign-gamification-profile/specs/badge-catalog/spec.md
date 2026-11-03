# Spec Delta

## Purpose

Der Abzeichenkatalog macht persönliche Erfolge, Bedingungen und Fortschritt verständlich sichtbar und bietet eine konsistente Struktur für weitere Abzeichen.

## ADDED Requirements

### Requirement: Badges are grouped by stable categories

Das System MUST Abzeichen mindestens in diese Kategorien gruppieren: Start & Entdecken, Runden-Meilensteine, Serien & Gewohnheiten, Treue & Langzeit, Saison & Ereignisse sowie Community & Teilen. Jede Badge-Definition MUST genau eine Hauptkategorie haben; die Übersicht DARF Kategorien ohne sichtbare Abzeichen nicht anzeigen.

#### Scenario: Participant browses categories

- **WHEN** ein Teilnehmer die Abzeichenübersicht öffnet
- **THEN** sieht er die Kategorien und die darin enthaltenen Abzeichen getrennt voneinander

### Requirement: Badge overview shows progress

Das System MUST in der persönlichen Übersicht die Zahl erreichter und verfügbarer Abzeichen sowie einen Fortschrittsbalken anzeigen.

#### Scenario: Progress count is shown

- **WHEN** ein Teilnehmer 8 von 23 verfügbaren Abzeichen erreicht hat
- **THEN** zeigt die Übersicht `8/23` und einen entsprechenden Fortschrittsbalken

### Requirement: Every badge has an individual visual mark

Jede Badge-Definition MUST eine individuell gestaltete Vektormarke statt Unicode-Emoji besitzen. Saisonale Vektormarken MUST je Jahresausgabe visuell variieren. Die Marke MUST in Übersicht und Detailseite erscheinen und für Screenreader dekorativ markiert sein; Badge-Name und Status bleiben als Text zugänglich.

#### Scenario: Badge icon is displayed accessibly

- **WHEN** ein Teilnehmer die Badge-Übersicht oder eine Badge-Detailseite öffnet
- **THEN** sieht er die individuell gezeichnete Vektormarke und kann den Badge-Namen unabhängig davon als Text wahrnehmen

### Requirement: One-off badges omit numeric progress

Abzeichen ohne stufenweisen Fortschritt MUST in Übersicht und Detailansicht keine künstliche Zählung wie `0/1` anzeigen.

#### Scenario: Seasonal one-off is not staged

- **WHEN** ein Teilnehmer ein noch nicht erreichtes eintägiges Saisonabzeichen betrachtet
- **THEN** wird sein Symbol und Status angezeigt, aber keine Fortschrittsanzeige `0/1`

### Requirement: Badge details explain achievement

Jedes Abzeichen MUST eine Detailansicht mit Name, Kategorie, Beschreibung, Bedingung, aktuellem Fortschritt und Zielwert anbieten, sofern das Abzeichen stufenweisen Fortschritt besitzt.

#### Scenario: Participant opens badge details

- **WHEN** ein Teilnehmer ein Abzeichen auswählt
- **THEN** sieht er die Bedingung und seinen Fortschritt, zum Beispiel `1/7`

### Requirement: Badge retention follows its achievement policy

Jede Badge-Definition MUST festlegen, ob sie den aktuellen Zählstand abbildet oder als historischer Erfolg erhalten bleibt. Korrigierbare Zähl-Badges können verschwinden; historische Badges bleiben nach dem Erreichen sichtbar.

#### Scenario: Count badge follows current data

- **WHEN** eine Korrektur den aktuellen Zählstand unter die Bedingung eines Zähl-Badges senkt
- **THEN** wird dieses Zähl-Badge nicht mehr als erreicht angezeigt

#### Scenario: Historical badge remains visible

- **WHEN** ein Teilnehmer ein historisches Badge erreicht und später eine zugrunde liegende Runde korrigiert wird
- **THEN** bleibt das historische Badge in seiner persönlichen Übersicht sichtbar

### Requirement: Level names are part of the catalog

Das System MUST jedem Level eine stabile, lokalisierbare Bezeichnung zuordnen und diese Bezeichnung gemeinsam mit der Levelnummer anzeigen.

#### Scenario: Named level is displayed

- **WHEN** ein Teilnehmer Level 2 erreicht
- **THEN** sieht er die konfigurierte Bezeichnung für Level 2 statt nur der Zahl
