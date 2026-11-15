import CoreLocation
import Foundation

@main
struct CheckWalkDistance {
    static func main() {
        let now = Date()
        func location(
            longitude: CLLocationDegrees,
            accuracy: CLLocationAccuracy = 5,
            timestamp: Date = now
        ) -> CLLocation {
            CLLocation(
                coordinate: CLLocationCoordinate2D(latitude: 0, longitude: longitude),
                altitude: 0,
                horizontalAccuracy: accuracy,
                verticalAccuracy: 5,
                timestamp: timestamp
            )
        }

        var accumulator = WalkDistanceAccumulator()
        accumulator.record(location(longitude: 0), now: now)
        accumulator.record(location(longitude: 0.00005), now: now)
        let firstSegment = accumulator.distanceMeters
        assert(firstSegment > 5 && firstSegment < 6)

        accumulator.record(location(longitude: 0.001, accuracy: 100), now: now)
        assert(accumulator.distanceMeters == firstSegment)

        accumulator.record(location(longitude: 0.0001), now: now)
        assert(accumulator.distanceMeters > 11 && accumulator.distanceMeters < 12)

        accumulator.record(location(longitude: 0.01, timestamp: now.addingTimeInterval(-61)), now: now)
        assert(accumulator.distanceMeters > 11 && accumulator.distanceMeters < 12)
    }
}
