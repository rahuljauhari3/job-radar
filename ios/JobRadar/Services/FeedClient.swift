import Foundation

enum Settings {
    static let defaultFeedURL = "https://raw.githubusercontent.com/rahuljauhari3/job-radar/data/feed.json"

    enum Key {
        static let feedURL = "feedURL"
        static let ntfyTopic = "ntfyTopic"
        static let notifyTiers = "notifyTiers"
        static let seenIDs = "seenIDs"
        static let notifiedIDs = "notifiedIDs"
    }

    static var defaults: UserDefaults { .standard }

    static var feedURL: URL? {
        if let override = ProcessInfo.processInfo.environment["JOBRADAR_FEED_URL"] { return URL(string: override) }
        return URL(string: defaults.string(forKey: Key.feedURL).flatMap { $0.isEmpty ? nil : $0 } ?? defaultFeedURL)
    }

    /// Tiers that get a local notification from background refresh. Defaults to A and B.
    static var notifyTiers: Set<String> {
        get { Set((defaults.string(forKey: Key.notifyTiers) ?? "AB").map(String.init)) }
        set { defaults.set(newValue.sorted().joined(), forKey: Key.notifyTiers) }
    }
}

/// Downloads `feed.json`, keeping the last good copy on disk for offline launches.
struct FeedClient {
    var session: URLSession = .shared
    var cacheURL: URL = FileManager.default.urls(for: .cachesDirectory, in: .userDomainMask)[0]
        .appendingPathComponent("feed.json")

    func fetch(from url: URL) async throws -> Feed {
        var request = URLRequest(url: url, cachePolicy: .reloadIgnoringLocalCacheData, timeoutInterval: 20)
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        let (data, response) = try await session.data(for: request)
        if let http = response as? HTTPURLResponse, !(200..<300).contains(http.statusCode) {
            throw URLError(.badServerResponse, userInfo: [NSLocalizedDescriptionKey: "Feed returned HTTP \(http.statusCode)"])
        }
        let feed = try FeedClient.decode(data)
        try? data.write(to: cacheURL, options: .atomic)
        return feed
    }

    func cached() -> Feed? {
        guard let data = try? Data(contentsOf: cacheURL) else { return nil }
        return try? FeedClient.decode(data)
    }

    static func decode(_ data: Data) throws -> Feed {
        try JSONDecoder().decode(Feed.self, from: data)
    }
}
