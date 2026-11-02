import Foundation
import Observation

@MainActor
@Observable
final class FeedStore {
    private(set) var jobs: [FeedJob] = []
    private(set) var generatedAt: Date?
    private(set) var isLoading = false
    private(set) var error: String?
    /// IDs present when the feed was last opened; anything else is "new".
    private(set) var seen: Set<String>

    private let client: FeedClient

    init(client: FeedClient = FeedClient()) {
        self.client = client
        seen = Set(Settings.defaults.stringArray(forKey: Settings.Key.seenIDs) ?? [])
        if let cached = client.cached() { apply(cached) }
    }

    func isNew(_ job: FeedJob) -> Bool { !seen.contains(job.id) }

    func job(id: String) -> FeedJob? { jobs.first { $0.id == id } }

    func refresh() async {
        guard let url = Settings.feedURL else {
            error = "Feed URL is not valid"
            return
        }
        isLoading = true
        defer { isLoading = false }
        do {
            apply(try await client.fetch(from: url))
            error = nil
        } catch {
            self.error = error.localizedDescription
        }
    }

    /// Call when the user has looked at the feed, so the next refresh's arrivals stand out.
    func markAllSeen() {
        seen.formUnion(jobs.map(\.id))
        let window = Set(jobs.map(\.id))
        Settings.defaults.set(Array(seen.intersection(window)), forKey: Settings.Key.seenIDs)
    }

    private func apply(_ feed: Feed) {
        jobs = feed.jobs
        generatedAt = Date(timeIntervalSince1970: feed.generatedAt)
        if seen.isEmpty {  // first launch: nothing is "new"
            seen = Set(feed.jobs.map(\.id))
            Settings.defaults.set(Array(seen), forKey: Settings.Key.seenIDs)
        }
    }
}
