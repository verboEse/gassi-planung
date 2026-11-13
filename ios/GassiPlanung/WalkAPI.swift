import Foundation

struct WalkPerson: Decodable {
    let id: Int
    let name: String
}

struct WalkMeResponse: Decodable {
    let person: WalkPerson
}

struct WalkDog: Decodable, Identifiable {
    let id: Int
    let name: String
    let walkNotes: String
}

struct WalkDogsResponse: Decodable {
    let dogs: [WalkDog]
}

struct WalkWindow: Decodable {
    let date: String
    let slot: String
}

struct ActiveWalk: Decodable {
    let date: String
    let slot: String?
    let walkType: String
    let startedAt: String
}

struct WalkStatus: Decodable {
    let active: ActiveWalk?
    let window: WalkWindow?
    let assigneeId: Int?
    let canStart: Bool
    let canStartExtra: Bool
}

struct WalkGamificationResponse: Decodable {
    let walkStatus: WalkStatus
}

struct WalkTakeover: Decodable {
    let walkDate: String
    let slot: String
    let requesterId: Int
    let assigneeId: Int
    let status: String
}

struct WalkTakeoversResponse: Decodable {
    let requests: [WalkTakeover]
}

struct WalkEndResponse: Decodable {
    let distanceMeters: Int?
    let personalRecord: Bool
    let newBadges: [String]
}

enum WalkAPIError: LocalizedError {
    case invalidServerAddress
    case response(status: Int, message: String)

    var isUnauthorized: Bool {
        if case let .response(status, _) = self {
            return status == 401
        }
        return false
    }

    var errorDescription: String? {
        switch self {
        case .invalidServerAddress:
            return "Gib eine gültige HTTPS-Adresse des Gassi-Planung-Servers ein."
        case let .response(_, message):
            return message
        }
    }
}

struct WalkAPI {
    private let baseURL: URL
    let serverHost: String
    private let session = URLSession.shared

    init(serverAddress: String) throws {
        guard let components = URLComponents(string: serverAddress.trimmingCharacters(in: .whitespacesAndNewlines)),
              let scheme = components.scheme?.lowercased(),
              let host = components.host?.lowercased(),
              components.user == nil,
              components.password == nil,
              components.query == nil,
              components.fragment == nil,
              components.path.isEmpty || components.path == "/",
              scheme == "https"
                || (scheme == "http" && ["localhost", "127.0.0.1", "::1"].contains(host)),
              let url = components.url else {
            throw WalkAPIError.invalidServerAddress
        }
        baseURL = url
        serverHost = host
    }

    func login(name: String, password: String) async throws {
        let body = LoginBody(displayName: name, password: password)
        let data = try JSONEncoder().encode(body)
        _ = try await send("/auth/login", method: "POST", body: data)
    }

    func me() async throws -> WalkMeResponse {
        try decode(await send("/api/me"))
    }

    func gamification() async throws -> WalkGamificationResponse {
        try decode(await send("/api/gamification"))
    }

    func dogs() async throws -> WalkDogsResponse {
        try decode(await send("/api/dogs"))
    }

    func takeovers() async throws -> WalkTakeoversResponse {
        try decode(await send("/api/walk-takeovers"))
    }

    func startWalk(extra: Bool) async throws {
        let query = extra ? [URLQueryItem(name: "walk_type", value: "extra")] : []
        _ = try await send("/api/walks/start", method: "POST", queryItems: query)
    }

    func endWalk(dogIDs: [Int], distanceMeters: Int?) async throws -> WalkEndResponse {
        let body = EndWalkBody(dogIDs: dogIDs, distanceMeters: distanceMeters)
        let data = try JSONEncoder().encode(body)
        return try decode(await send("/api/walks/end", method: "POST", body: data))
    }

    func logout() async throws {
        _ = try await send("/auth/logout", method: "POST")
    }

    private func send(
        _ path: String,
        method: String = "GET",
        queryItems: [URLQueryItem] = [],
        body: Data? = nil
    ) async throws -> Data {
        var components = URLComponents(url: baseURL, resolvingAgainstBaseURL: false)
        components?.path = path
        components?.queryItems = queryItems.isEmpty ? nil : queryItems
        guard let url = components?.url else {
            throw WalkAPIError.invalidServerAddress
        }

        var request = URLRequest(url: url, timeoutInterval: 30)
        request.httpMethod = method
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        if let body {
            request.httpBody = body
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        }

        let (data, response) = try await session.data(for: request)
        guard let response = response as? HTTPURLResponse else {
            throw WalkAPIError.response(status: 0, message: "Ungültige Serverantwort.")
        }
        guard (200..<300).contains(response.statusCode) else {
            let message = (try? decode(data, as: ErrorBody.self).detail)
                ?? "Serverfehler (\(response.statusCode))."
            throw WalkAPIError.response(status: response.statusCode, message: message)
        }
        return data
    }

    private func decode<T: Decodable>(_ data: Data, as type: T.Type = T.self) throws -> T {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(type, from: data)
    }
}

private struct LoginBody: Encodable {
    let displayName: String
    let password: String

    enum CodingKeys: String, CodingKey {
        case displayName = "display_name"
        case password
    }
}

private struct EndWalkBody: Encodable {
    let dogIDs: [Int]
    let distanceMeters: Int?

    enum CodingKeys: String, CodingKey {
        case dogIDs = "dog_ids"
        case distanceMeters = "distance_meters"
    }
}

private struct ErrorBody: Decodable {
    let detail: String?
}
