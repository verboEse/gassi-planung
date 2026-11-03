# Tasks

## 1. iCal-Erinnerungen

- [x] 1.1 Die Erinnerungseinstellung in den persönlichen iCal-Feed übernehmen und für Einzel- sowie Wiederholungstermine bedingt `VALARM` mit `TRIGGER:-PT15M` ausgeben; Tests müssen aktive/deaktivierte Einstellungen, beide Terminarten und Zeitzonenwechsel abdecken.
- [x] 1.2 README zum iCal-Alarm, zum verzögerten Abruf abonnierter Kalender und zu den Grenzen unterschiedlicher Kalender-Clients aktualisieren; dokumentiertes Verhalten mit Feed und Spec abgleichen.

## 2. Browser-Push-Abos

- [x] 2.1 SQLite-Migration und Datenbankzugriff für mehrere Browser-Abos pro Teilnehmer ergänzen; Migration, Speichern, Auflisten und Entfernen der Abos testen.
- [x] 2.2 Authentifizierte API zum Registrieren und Entfernen eigener Browser-Abos sowie Bereitstellung des öffentlichen VAPID-Schlüssels ergänzen; API-Tests müssen Fremdzugriff ablehnen und ungültige Abos zurückweisen.
- [x] 2.3 Root-scoped Service Worker und Profil-Oberfläche für explizite Browser-Berechtigung sowie Abo-Verwaltung ergänzen; Browserprüfung muss Anmeldung, Erteilen/Verweigern der Berechtigung und Deaktivieren der Erinnerung abdecken.
- [x] 2.4 VAPID-Konfiguration über Deployment-Secrets und README einführen; prüfen, dass der private Schlüssel nicht im Repository liegt und die dokumentierte HTTPS-Konfiguration nachvollziehbar ist.

## 3. Geplante Zustellung

- [x] 3.1 Persistente Reminder-Outbox und Plan-Reconciliation mit eindeutigem Schlüssel pro Teilnehmer, Datum und Timeslot ergänzen; Tests müssen 15-Minuten-Fälligkeit in `Europe/Berlin`, Sommer-/Winterzeit, Duplikatvermeidung und geänderte Zuweisungen prüfen.
- [x] 3.2 Einzelprozess-Dispatcher im FastAPI-Lifespan implementieren, der vor jedem Versand Einstellung und Zuweisung erneut prüft, Web Push versendet, temporäre Fehler begrenzt wiederholt, ungültige Abos entfernt und nach Timeslot-Beginn fällige Jobs verwirft; Tests mit Fake-Sender müssen diese Fälle abdecken.
- [x] 3.3 README um Zustellverhalten, Berechtigungsanforderungen, mögliche doppelte Anzeige durch Web-Push und Kalender-App sowie Betrieb des Dispatchers ergänzen; Angaben gegen Implementierung und Specs prüfen.

## 4. Integration

- [x] 4.1 iCal- und Push-Pfade zusammen mit aktivierter und deaktivierter Erinnerungseinstellung integrieren und gezielte Tests, JavaScript-Syntaxprüfung sowie `openspec validate send-reminders-and-push-notifications --strict` erfolgreich ausführen.
