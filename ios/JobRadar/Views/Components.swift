import SwiftUI

extension FeedJob {
    var tierColor: Color {
        switch tier {
        case "A": return .orange
        case "B": return .blue
        default: return .gray
        }
    }
}

struct TierBadge: View {
    let job: FeedJob

    var body: some View {
        HStack(spacing: 3) {
            Text(job.tier).fontWeight(.heavy)
            Text("\(job.score)").monospacedDigit()
        }
        .font(.caption2)
        .padding(.horizontal, 6)
        .padding(.vertical, 2)
        .foregroundStyle(job.tierColor)
        .background(job.tierColor.opacity(0.15), in: Capsule())
        .accessibilityLabel("\(job.tierLabel), score \(job.score)")
    }
}

struct JobRow: View {
    let job: FeedJob
    let isNew: Bool
    var status: ApplicationStatus?

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack(alignment: .firstTextBaseline) {
                if isNew {
                    Circle().fill(.tint).frame(width: 7, height: 7).accessibilityLabel("New")
                }
                Text(job.company).font(.subheadline.weight(.semibold)).lineLimit(1)
                Spacer()
                if let status {
                    Image(systemName: status.symbol).font(.caption).foregroundStyle(.secondary)
                }
                TierBadge(job: job)
            }
            Text(job.title).font(.body).lineLimit(2)
            HStack(spacing: 6) {
                Text(job.locationLine).lineLimit(1)
                if let term = job.terms.first { Text("· \(term)") }
                Spacer()
                Text(job.firstSeenDate, format: .relative(presentation: .numeric, unitsStyle: .narrow))
            }
            .font(.caption)
            .foregroundStyle(.secondary)
            if !job.flags.isEmpty {
                Label(job.flags.joined(separator: " · "), systemImage: job.hasWarning ? "exclamationmark.triangle" : "info.circle")
                    .font(.caption2)
                    .foregroundStyle(job.hasWarning ? .orange : .secondary)
                    .lineLimit(1)
            }
        }
        .padding(.vertical, 2)
    }
}
