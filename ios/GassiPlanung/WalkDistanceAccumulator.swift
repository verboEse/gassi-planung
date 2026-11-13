import CoreLocation
import Foundation

struct WalkDistanceAccumulator {
    private(set) var distanceMeters: CLLocationDistance
    private var lastLocation: CLLocation?

    init(distanceMeters: CLLocationDistance = 0) {
        self.distanceMeters = max(0, distanceMeters)
    }

    mutating func record(_ location: CLLocation, now: Date = Date()) {
        let age = now.timeIntervalSince(location.timestamp)
        guard location.horizontalAccuracy >= 0,
              location.horizontalAccuracy <= 50,
              age >= -15,
              age <= 60 else {
            return
        }

        if let lastLocation {
            let segment = lastLocation.distance(from: location)
            if segment >= 3 {
                distanceMeters += segment
            }
        }
        lastLocation = location
    }

    mutating func reset() {
        distanceMeters = 0
        lastLocation = nil
    }
}
