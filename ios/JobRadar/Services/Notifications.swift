import BackgroundTasks
import Foundation
import UserNotifications

/// Local notifications for new matches. A fallback for when the ntfy app isn't set up:
/// iOS decides when background refresh runs, so these can lag by hours.
enum LocalNotifier {
    static let maxPerCheck = 8

    static func requestPermission() async -> Bool {
        (try? await UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound, .badge])) ?? false
    }

    /// Posts one notification per new matching job (and a summary for the rest). Returns how many jobs were new.
    @discardableResult
    static func notifyNewJobs(in feed: Feed) async -> Int {
        let defaults = Settings.defaults
        let notified = Set(defaults.stringArray(forKey: Settings.Key.notifiedIDs) ?? [])
        let seen = Set(defaults.stringArray(forKey: Settings.Key.seenIDs) ?? []).union(notified)
        let fresh = NewJobs.toNotify(feed.jobs, seen: seen, tiers: Settings.notifyTiers)
        guard !fresh.isEmpty else { return 0 }

        let center = UNUserNotificationCenter.current()
        for job in fresh.prefix(maxPerCheck) {
            let content = UNMutableNotificationContent()
            content.title = "\(job.company) — \(job.title)"
            content.body = [job.locationLine, job.terms.first, "\(job.tierLabel) · \(job.score)"]
                .compactMap { $0 }.joined(separator: " · ")
            content.sound = job.tier == "A" ? .defaultCritical : .default
            content.userInfo = ["jobID": job.id]
            content.threadIdentifier = "tier-\(job.tier)"
            try? await center.add(UNNotificationRequest(identifier: "job-\(job.id)", content: content, trigger: nil))
        }
        if fresh.count > maxPerCheck {
            let content = UNMutableNotificationContent()
            content.title = "\(fresh.count - maxPerCheck) more new matches"
            content.body = fresh.dropFirst(maxPerCheck).prefix(4).map(\.company).joined(separator: ", ")
            try? await center.add(UNNotificationRequest(identifier: "summary-\(Date.now.timeIntervalSince1970)", content: content, trigger: nil))
        }
        let window = Set(feed.jobs.map(\.id))
        defaults.set(Array(notified.union(fresh.map(\.id)).intersection(window)), forKey: Settings.Key.notifiedIDs)
        return fresh.count
    }
}

enum BackgroundRefresh {
    static let identifier = "com.rahuljauhari.JobRadar.refresh"

    static func schedule() {
        let request = BGAppRefreshTaskRequest(identifier: identifier)
        request.earliestBeginDate = Date(timeIntervalSinceNow: 15 * 60)
        try? BGTaskScheduler.shared.submit(request)
    }

    /// One background check: fetch the feed, notify, reschedule.
    static func run() async {
        schedule()
        guard let url = Settings.feedURL, let feed = try? await FeedClient().fetch(from: url) else { return }
        await LocalNotifier.notifyNewJobs(in: feed)
    }
}
