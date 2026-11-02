import SwiftData
import SwiftUI

struct TrackerView: View {
    @Environment(\.modelContext) private var context
    @Environment(\.openURL) private var openURL
    @Query(sort: \TrackedJob.updatedAt, order: .reverse) private var all: [TrackedJob]
    @State private var status: ApplicationStatus = .applied

    var body: some View {
        let funnel = Funnel(all)
        NavigationStack {
            List {
                Section {
                    FunnelView(funnel: funnel)
                } footer: {
                    Text("OA rate counts OA, interview and offer stages against everything you applied to.")
                }
                Section {
                    Picker("Status", selection: $status) {
                        ForEach(ApplicationStatus.allCases) { s in
                            Text("\(s.label) \(funnel.count(s))").tag(s)
                        }
                    }
                    .pickerStyle(.menu)
                }
                let rows = all.filter { $0.status == status }
                if rows.isEmpty {
                    Text("Nothing here yet. Swipe right on a posting in the feed to mark it applied.")
                        .foregroundStyle(.secondary)
                }
                ForEach(rows) { job in
                    VStack(alignment: .leading, spacing: 2) {
                        Text(job.company).font(.subheadline.weight(.semibold))
                        Text(job.title).lineLimit(2)
                        Text("Updated \(job.updatedAt.formatted(.relative(presentation: .named)))")
                            .font(.caption).foregroundStyle(.secondary)
                    }
                    .contentShape(Rectangle())
                    .onTapGesture { if let url = URL(string: job.url) { openURL(url) } }
                    .contextMenu {
                        ForEach(ApplicationStatus.allCases) { s in
                            Button { job.status = s; try? context.save() } label: { Label(s.label, systemImage: s.symbol) }
                        }
                    }
                    .swipeActions {
                        if let next = funnel.next(after: job.status) {
                            Button { job.status = next; try? context.save() } label: { Label(next.label, systemImage: next.symbol) }
                                .tint(.green)
                        }
                        Button { job.status = .rejected; try? context.save() } label: { Label("Rejected", systemImage: "xmark") }
                            .tint(.red)
                    }
                }
            }
            .navigationTitle("Tracker")
        }
    }
}

/// Application counts and conversion rates.
struct Funnel {
    let counts: [ApplicationStatus: Int]

    init(_ jobs: [TrackedJob]) {
        counts = Dictionary(grouping: jobs, by: \.status).mapValues(\.count)
    }

    func count(_ s: ApplicationStatus) -> Int { counts[s, default: 0] }

    var applied: Int { ApplicationStatus.pipeline.map(count).reduce(0, +) }
    var reachedOA: Int { count(.oa) + count(.interview) + count(.offer) }
    var reachedInterview: Int { count(.interview) + count(.offer) }

    func rate(_ n: Int) -> String {
        applied == 0 ? "–" : (Double(n) / Double(applied)).formatted(.percent.precision(.fractionLength(0)))
    }

    func next(after s: ApplicationStatus) -> ApplicationStatus? {
        switch s {
        case .saved: return .applied
        case .applied: return .oa
        case .oa: return .interview
        case .interview: return .offer
        default: return nil
        }
    }
}

struct FunnelView: View {
    let funnel: Funnel

    var body: some View {
        HStack {
            stat("Applied", "\(funnel.applied)")
            Divider()
            stat("OA rate", funnel.rate(funnel.reachedOA))
            Divider()
            stat("Interview rate", funnel.rate(funnel.reachedInterview))
        }
        .frame(maxWidth: .infinity)
    }

    private func stat(_ label: String, _ value: String) -> some View {
        VStack {
            Text(value).font(.title2.weight(.semibold)).monospacedDigit()
            Text(label).font(.caption).foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity)
    }
}
