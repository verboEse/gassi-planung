import Combine
import CoreLocation
import Foundation

final class WalkLocationTracker: NSObject, ObservableObject, CLLocationManagerDelegate {
    @Published private(set) var distanceMeters: CLLocationDistance = 0
    @Published private(set) var authorizationStatus: CLAuthorizationStatus = .notDetermined
    @Published private(set) var locationError: String?

    private let manager = CLLocationManager()
    private var accumulator = WalkDistanceAccumulator()
    private var distanceKey: String?

    override init() {
        super.init()
        manager.delegate = self
        manager.activityType = .fitness
        manager.desiredAccuracy = kCLLocationAccuracyBest
        manager.distanceFilter = 5
        manager.pausesLocationUpdatesAutomatically = false
        manager.allowsBackgroundLocationUpdates = true
        #if os(iOS)
        manager.showsBackgroundLocationIndicator = true
        #endif
        authorizationStatus = manager.authorizationStatus
    }

    func requestAlwaysAuthorization() {
        manager.requestAlwaysAuthorization()
    }

    func start(for key: String) {
        distanceKey = key
        accumulator.reset()
        distanceMeters = 0
        locationError = nil
        UserDefaults.standard.set(0.0, forKey: key)
        startLocationUpdates()
    }

    func resume(for key: String) {
        if distanceKey == key {
            startLocationUpdates()
            return
        }
        distanceKey = key
        let restoredDistance = UserDefaults.standard.double(forKey: key)
        accumulator = WalkDistanceAccumulator(distanceMeters: restoredDistance)
        distanceMeters = restoredDistance
        locationError = nil
        startLocationUpdates()
    }

    func stopAndReset(for key: String? = nil) {
        manager.stopUpdatingLocation()
        accumulator.reset()
        distanceMeters = 0
        locationError = nil
        if let key = key ?? distanceKey {
            UserDefaults.standard.removeObject(forKey: key)
        }
        distanceKey = nil
    }

    func locationManagerDidChangeAuthorization(_ manager: CLLocationManager) {
        let status = manager.authorizationStatus
        DispatchQueue.main.async { [weak self] in
            self?.authorizationStatus = status
        }
    }

    func locationManager(_ manager: CLLocationManager, didUpdateLocations locations: [CLLocation]) {
        DispatchQueue.main.async { [weak self] in
            guard let self else { return }
            for location in locations {
                self.accumulator.record(location)
            }
            self.distanceMeters = self.accumulator.distanceMeters
            if let distanceKey = self.distanceKey {
                UserDefaults.standard.set(self.distanceMeters, forKey: distanceKey)
            }
            self.locationError = nil
        }
    }

    func locationManager(_ manager: CLLocationManager, didFailWithError error: Error) {
        let message = error.localizedDescription
        DispatchQueue.main.async { [weak self] in
            self?.locationError = message
        }
    }

    private func startLocationUpdates() {
        guard CLLocationManager.locationServicesEnabled() else {
            locationError = "Die Ortungsdienste sind auf diesem iPhone deaktiviert."
            return
        }
        guard manager.authorizationStatus == .authorizedAlways else {
            locationError = "Erlaube den Standortzugriff „Immer“, um die Strecke bei gesperrtem Bildschirm zu messen."
            return
        }
        manager.startUpdatingLocation()
    }
}
