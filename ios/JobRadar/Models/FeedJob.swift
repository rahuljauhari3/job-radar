import Foundation

/// One posting as published by the poller in `feed.json`.
struct FeedJob: Codable, Identifiable, Hashable {
    struct Source: Codable, Hashable {
        let name: String
        let url: String
        let kind: String
    }

    let id: String
    let company: String
    let title: String
    let url: String
    let locations: [String]
    let terms: [String]
    let postedAt: Double?
    let sponsorship: String?
    let degrees: [String]
    let category: String?
    let active: Bool
    let tier: String
    let score: Int
    let reasons: [String]
    let flags: [String]
    let snippet: String
    let firstSeen: Double
    let sources: [Source]

    enum CodingKeys: String, CodingKey {
        case id, company, title, url, locations, terms, sponsorship, degrees, category, active
        case tier, score, reasons, flags, snippet, sources
        case postedAt = "posted_at"
        case firstSeen = "first_seen"
    }

    var tierLabel: String {
        switch tier {
        case "A": return "Core fit"
        case "B": return "Good fit"
        default: return "Stretch"
        }
    }

    var firstSeenDate: Date { Date(timeIntervalSince1970: firstSeen) }
    var postedDate: Date? { postedAt.map { Date(timeIntervalSince1970: $0) } }
    var applyURL: URL? { URL(string: url) }
    var locationLine: String { locations.isEmpty ? "Location not listed" : locations.prefix(3).joined(separator: " · ") }
    var hasWarning: Bool { flags.contains { $0.contains("citizenship") || $0.contains("sponsorship") } }
}

struct Feed: Codable {
    let version: Int
    let generatedAt: Double
    let jobs: [FeedJob]

    enum CodingKeys: String, CodingKey {
        case version, jobs
        case generatedAt = "generated_at"
    }
}
