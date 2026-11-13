import Combine
import CoreLocation
import Foundation

@MainActor
final class WalkStore: ObservableObject {
    static let defaultServerAddress = "https://gassiplan.verboese.de"
    private static let serverAddressKey = "gassi.serverAddress"
    private static let distanceBadgeIDs: Set<String> = [
        "five-kilometer-walk",
        "ten-kilometer-walk",
        "twenty-kilometer-walk",
    ]

    @Published var serverAddress: String {
        didSet { UserDefaults.standard.set(serverAddress, forKey: Self.serverAddressKey) }
    }
    @Published var displayName = ""
    @Published var password = ""
    @Published private(set) var person: WalkPerson?
    @Published private(set) var status: WalkStatus?
    @Published private(set) var dogs: [WalkDog] = []
    @Published private(set) var takeovers: [WalkTakeover] = []
    @Published var selectedDogIDs: Set<Int> = []
    @Published private(set) var isLoading = false
    @Published var errorMessage: String?
    @Published var successMessage: String?
    @Published var isGuidancePresented = false
    @Published private(set) var guidanceMessage = ""

    let locationTracker: WalkLocationTracker
    private var api: WalkAPI?
    private var pendingExtra = false

    init(locationTracker: WalkLocationTracker = WalkLocationTracker()) {
        self.locationTracker = locationTracker
        serverAddress = UserDefaults.standard.string(forKey: Self.serverAddressKey)
            ?? Self.defaultServerAddress
    }

    var canStartPlanned: Bool {
        guard let status,
              status.canStart,
              let window = status.window,
              let person else {
            return false
        }
        let currentRequests = takeovers.filter {
            $0.walkDate == window.date && $0.slot == window.slot
        }
        if status.assigneeId == person.id {
            return !currentRequests.contains { $0.status == "approved" }
        }
        return currentRequests.contains {
            $0.requesterId == person.id && $0.status == "approved"
        }
    }

    var canStartExtra: Bool {
        status?.canStartExtra == true
    }

    var currentWindowLabel: String {
        guard let window = status?.window else {
            return "Zurzeit gibt es kein geplantes Zeitfenster."
        }
        return "Aktuelles Zeitfenster: \(slotLabel(window.slot))"
    }

    var activeWalkLabel: String {
        guard let active = status?.active else { return "" }
        return active.walkType == "extra"
            ? "Extra-Runde läuft"
            : "Gassirunde \(slotLabel(active.slot ?? "")) läuft"
    }

    var formattedDistance: String {
        Self.formatDistance(locationTracker.distanceMeters)
    }

    func restoreSession() async {
        guard person == nil else { return }
        do {
            let api = try WalkAPI(serverAddress: serverAddress)
            self.api = api
            person = try await api.me().person
            await reload()
        } catch let error as WalkAPIError where error.isUnauthorized {
            api = nil
            person = nil
        } catch {
            api = nil
            person = nil
            errorMessage = error.localizedDescription
        }
    }

    func login() async {
        guard !isLoading else { return }
        errorMessage = nil
        successMessage = nil
        isLoading = true
        defer { isLoading = false }
        do {
            let api = try WalkAPI(serverAddress: serverAddress)
            try await api.login(
                name: displayName.trimmingCharacters(in: .whitespacesAndNewlines),
                password: password
            )
            self.api = api
            person = try await api.me().person
            password = ""
            await reload()
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func logout() async {
        guard status?.active == nil else {
            errorMessage = "Beende zuerst die aktive Gassirunde."
            return
        }
        guard let api else { return }
        isLoading = true
        defer { isLoading = false }
        do {
            if let person {
                locationTracker.stopAndReset(for: distanceKey(api: api, person: person))
            }
            try await api.logout()
            self.api = nil
            person = nil
            status = nil
            dogs = []
            takeovers = []
            selectedDogIDs = []
            successMessage = nil
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func refresh() async {
        await reload()
    }

    func startWalk(extra: Bool) async {
        guard !isLoading else { return }
        errorMessage = nil
        successMessage = nil
        guard ensureLocationPermission() else { return }

        pendingExtra = extra
        let notes = dogs.compactMap { dog -> String? in
            let note = dog.walkNotes.trimmingCharacters(in: .whitespacesAndNewlines)
            return note.isEmpty ? nil : "\(dog.name):\n\(note)"
        }
        if !notes.isEmpty {
            guidanceMessage = notes.joined(separator: "\n\n")
            isGuidancePresented = true
        } else {
            await startWalkNow(extra: extra)
        }
    }

    func cancelStart() {
        isGuidancePresented = false
        pendingExtra = false
    }

    func confirmStart() async {
        isGuidancePresented = false
        await startWalkNow(extra: pendingExtra)
    }

    func endWalk() async {
        guard !isLoading, status?.active != nil, let api, let person else { return }
        errorMessage = nil
        successMessage = nil
        let finishedExtraWalk = status?.active?.walkType == "extra"
        isLoading = true
        defer { isLoading = false }

        let roundedDistance = Int(locationTracker.distanceMeters.rounded())
        do {
            let result = try await api.endWalk(
                dogIDs: selectedDogIDs.sorted(),
                distanceMeters: roundedDistance > 0 ? roundedDistance : nil
            )
            locationTracker.stopAndReset(for: distanceKey(api: api, person: person))
            selectedDogIDs = []

            var messages = [finishedExtraWalk ? "Extra-Runde beendet." : "Gassirunde beendet."]
            if let distance = result.distanceMeters {
                messages.append("Strecke: \(Self.formatDistance(Double(distance))).")
            }
            if result.personalRecord {
                messages.append("Du hast Deinen Streckenrekord gebrochen.")
            }
            if !Self.distanceBadgeIDs.isDisjoint(with: result.newBadges) {
                messages.append("Du hast ein Langstrecken-Abzeichen freigeschaltet.")
            }
            successMessage = messages.joined(separator: " ")
            await reload()
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    private func startWalkNow(extra: Bool) async {
        guard !isLoading, let api, let person else { return }
        guard ensureLocationPermission() else { return }
        errorMessage = nil
        isLoading = true
        defer { isLoading = false }
        do {
            try await api.startWalk(extra: extra)
            selectedDogIDs = []
            locationTracker.start(for: distanceKey(api: api, person: person))
            successMessage = extra ? "Extra-Runde gestartet." : "Gassirunde gestartet."
            await reload()
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    private func ensureLocationPermission() -> Bool {
        guard CLLocationManager.locationServicesEnabled() else {
            errorMessage = "Aktiviere die Ortungsdienste in den iPhone-Einstellungen."
            return false
        }
        switch locationTracker.authorizationStatus {
        case .authorizedAlways:
            return true
        case .notDetermined, .authorizedWhenInUse:
            locationTracker.requestAlwaysAuthorization()
            errorMessage = "Erlaube den Standortzugriff „Immer“ und starte die Runde danach erneut."
            return false
        case .denied, .restricted:
            errorMessage = "Erlaube den Standortzugriff „Immer“ in den iPhone-Einstellungen."
            return false
        @unknown default:
            errorMessage = "Der Standortzugriff ist auf diesem iPhone nicht verfügbar."
            return false
        }
    }

    private func reload() async {
        guard let api, let person else { return }
        do {
            async let gamification = api.gamification()
            async let dogResponse = api.dogs()
            async let takeoverResponse = api.takeovers()
            let (gamificationResult, dogResult, takeoverResult) =
                try await (gamification, dogResponse, takeoverResponse)
            status = gamificationResult.walkStatus
            dogs = dogResult.dogs
            takeovers = takeoverResult.requests
            let key = distanceKey(api: api, person: person)
            if gamificationResult.walkStatus.active != nil {
                locationTracker.resume(for: key)
            } else {
                locationTracker.stopAndReset(for: key)
            }
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    private func distanceKey(api: WalkAPI, person: WalkPerson) -> String {
        "gassi.walk-distance.\(api.serverHost).\(person.id)"
    }

    private func slotLabel(_ slot: String) -> String {
        switch slot {
        case "morning": return "Morgens"
        case "noon": return "Mittags"
        case "evening": return "Abends"
        default: return "Gassirunde"
        }
    }

    private static func formatDistance(_ meters: Double) -> String {
        let formatter = NumberFormatter()
        formatter.locale = Locale.current
        formatter.numberStyle = .decimal
        formatter.maximumFractionDigits = 1
        formatter.minimumFractionDigits = 1
        let kilometers = formatter.string(from: NSNumber(value: meters / 1000)) ?? "0,0"
        return "\(kilometers) km"
    }
}
