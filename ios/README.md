# iOS-Begleit-App

Die native iOS-Begleit-App startet und beendet geplante Runden sowie
Extra-Runden über die bestehende, angemeldete API. Mit Core-Location-
Hintergrundaktualisierungen wird die Strecke auch bei gesperrtem Bildschirm
weiter erfasst.

## Erstellen und signieren

Öffne `GassiPlanung/GassiPlanung.xcodeproj` in Xcode. Die App erfordert
iOS 17 oder neuer. Signiere das Ziel `GassiPlanung` mit dem Apple-Entwicklerteam,
das die App verteilen soll. Gib beim ersten Start die HTTPS-Adresse des Servers
ein und melde dich mit einem bestehenden Gassi-Planung-Konto an.

Die App verwendet das signierte Sitzungscookie des Servers und speichert das
Passwort nicht. Sie benötigt die iOS-Standortberechtigung **Immer** und den
Hintergrundmodus für Standortaktualisierungen. Ohne Standortberechtigung startet
die App keine Gassirunde auf dem Server.

## Strecke und Datenschutz

Die App filtert veraltete und ungenaue Standortmessungen und summiert die
Strecke im Arbeitsspeicher. Während einer aktiven Runde wird lokal nur die
Gesamtstrecke in Metern gespeichert, damit sie nach einem Neustart der App
wiederhergestellt werden kann. Koordinaten werden weder gespeichert noch an den
Server übertragen. Beim Beenden der Runde wird ausschließlich der optionale
Wert `distance_meters` zusammen mit dem bestehenden Rundeneintrag übertragen.

Langstrecken-Abzeichen werden für einzelne Runden ab 5, 10 und 20 km vergeben.
Einen neuen persönlichen Streckenrekord meldet die App, sobald der Server den
Rundenabschluss bestätigt hat. Wurde keine brauchbare GPS-Messung empfangen,
kann die Runde trotzdem ohne Streckenangabe beendet werden.

Der gezielte Selbsttest für die Streckenberechnung lässt sich unter macOS
folgendermaßen ausführen:

```sh
swiftc ios/GassiPlanung/WalkDistanceAccumulator.swift tests/check_walk_distance.swift -o /tmp/check-walk-distance
/tmp/check-walk-distance
```
