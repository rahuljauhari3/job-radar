import Foundation
import SwiftData

/// Where an application stands. Ordered as a funnel.
enum ApplicationStatus: String, Codable, CaseIterable, Identifiable {
    case saved, applied, oa, interview, offer, rejected, hidden

    var id: String { rawValue }

    var label: String {
        switch self {
        case .saved: return "Saved"
        case .applied: return "Applied"
        case .oa: return "OA"
        case .interview: return "Interview"
        case .offer: return "Offer"
        case .rejected: return "Rejected"
        case .hidden: return "Hidden"
        }
    }

    var symbol: String {
        switch self {
        case .saved: return "bookmark"
        case .applied: return "paperplane"
        case .oa: return "laptopcomputer"
        case .interview: return "person.2"
        case .offer: return "star"
        case .rejected: return "xmark.circle"
        case .hidden: return "eye.slash"
        }
    }

    /// Statuses that mean you sent an application.
    static let pipeline: [ApplicationStatus] = [.applied, .oa, .interview, .offer, .rejected]
}

/// A posting you acted on. Kept on device, independent of the feed window.
@Model
final class TrackedJob {
    @Attribute(.unique) var jobID: String
    var company: String
    var title: String
    var url: String
    var tier: String
    var statusRaw: String
    var createdAt: Date
    var updatedAt: Date
    var appliedAt: Date?
    var notes: String

    init(job: FeedJob, status: ApplicationStatus, now: Date = .now) {
        jobID = job.id
        company = job.company
        title = job.title
        url = job.url
        tier = job.tier
        statusRaw = status.rawValue
        createdAt = now
        updatedAt = now
        appliedAt = status == .saved || status == .hidden ? nil : now
        notes = ""
    }

    var status: ApplicationStatus {
        get { ApplicationStatus(rawValue: statusRaw) ?? .saved }
        set {
            statusRaw = newValue.rawValue
            updatedAt = .now
            if appliedAt == nil, ApplicationStatus.pipeline.contains(newValue) { appliedAt = .now }
        }
    }
}
