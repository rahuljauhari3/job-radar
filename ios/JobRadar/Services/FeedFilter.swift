import Foundation

/// What the feed list shows. Pure, so it is unit tested.
struct FeedFilter: Equatable {
    var tiers: Set<String> = ["A", "B", "C"]
    var search = ""
    var hideTracked = true
    var hideWarnings = false
    var onlyCoop = false

    func apply(_ jobs: [FeedJob], tracked: Set<String>) -> [FeedJob] {
        let query = search.trimmingCharacters(in: .whitespaces).lowercased()
        return jobs.filter { job in
            guard tiers.contains(job.tier), job.active else { return false }
            if hideTracked, tracked.contains(job.id) { return false }
            if hideWarnings, job.hasWarning { return false }
            if onlyCoop, !(job.title + " " + job.terms.joined(separator: " ")).lowercased().contains("co-op") { return false }
            if !query.isEmpty {
                let haystack = [job.company, job.title, job.locationLine, job.reasons.joined(separator: " ")]
                    .joined(separator: " ").lowercased()
                return query.split(separator: " ").allSatisfy { haystack.contains($0) }
            }
            return true
        }
    }

    /// Groups jobs by the calendar day they were first seen, newest day first.
    static func byDay(_ jobs: [FeedJob], calendar: Calendar = .current) -> [(day: Date, jobs: [FeedJob])] {
        let groups = Dictionary(grouping: jobs) { calendar.startOfDay(for: $0.firstSeenDate) }
        return groups.keys.sorted(by: >).map { day in
            (day, groups[day]!.sorted { ($0.firstSeen, $0.score) > ($1.firstSeen, $1.score) })
        }
    }
}

/// Jobs that arrived since the last check, for "new" badges and local notifications.
enum NewJobs {
    static func unseen(_ jobs: [FeedJob], seen: Set<String>) -> [FeedJob] {
        jobs.filter { !seen.contains($0.id) }
    }

    static func toNotify(_ jobs: [FeedJob], seen: Set<String>, tiers: Set<String>) -> [FeedJob] {
        unseen(jobs, seen: seen)
            .filter { tiers.contains($0.tier) && $0.active && !$0.flags.contains("US citizenship/clearance") }
            .sorted { $0.score > $1.score }
    }
}
