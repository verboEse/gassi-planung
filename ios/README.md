# iOS companion app

The native iOS companion app starts and ends planned or extra walks through the
existing authenticated API. It uses Core Location background updates so a walk
continues to be measured while the screen is locked.

## Build and sign

Open `GassiPlanung/GassiPlanung.xcodeproj` in Xcode. The deployment target is
iOS 17. Sign the `GassiPlanung` target with the Apple development team that will
distribute the app. At first launch, enter the HTTPS address of the server and
sign in with an existing Gassi-Planung account.

The app uses the server's signed session cookie; it does not save the password.
It requires the iOS location permission **Always** and the Location Updates
background mode. If location permission is unavailable, the app does not start
a server-side walk.

## Distance and privacy

The app filters stale or inaccurate location samples and accumulates distance
in memory. While a walk is active, only the aggregate meter count is saved
locally so it can be restored after the app restarts. Coordinates are neither
persisted nor sent to the server. Ending a walk sends only the optional
`distance_meters` value with its existing walk completion.

Long-distance badges are awarded at 5, 10, and 20 km per walk. A new personal
distance record is reported in the app after the server confirms the completion.
If no usable GPS sample was received, the walk can still be completed without
a distance value.

The accumulator's focused self-check can be run on macOS with:

```sh
swiftc ios/GassiPlanung/WalkDistanceAccumulator.swift tests/check_walk_distance.swift -o /tmp/check-walk-distance
/tmp/check-walk-distance
```
