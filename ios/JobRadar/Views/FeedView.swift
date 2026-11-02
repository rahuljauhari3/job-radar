import SwiftData
import SwiftUI

struct FeedView: View {
    @Environment(FeedStore.self) private var store
    @Environment(Router.self) private var router
    @Environment(\.modelContext) private var context
    @Query private var tracked: [TrackedJob]
    @State private var filter = FeedFilter()
    @State private var path: [FeedJob] = []

    private var trackedByID: [String: TrackedJob] {
        Dictionary(tracked.map { ($0.jobID, $0) }, uniquingKeysWith: { a, _ in a })
    }

    var body: some View {
        let visible = filter.apply(store.jobs, tracked: Set(trackedByID.keys))
        NavigationStack(path: $path) {
            List {
                Section {
                    TierPicker(selection: $filter.tiers)
                } footer: {
                    statusLine(count: visible.count)
                }
                ForEach(FeedFilter.byDay(visible), id: \.day) { group in
                    Section(group.day.formatted(.dateTime.weekday(.wide).month().day())) {
                        ForEach(group.jobs) { job in
                            NavigationLink(value: job) {
                                JobRow(job: job, isNew: store.isNew(job), status: trackedByID[job.id]?.status)
                            }
                            .accessibilityIdentifier("job-row")
                            .swipeActions(edge: .leading) {
                                Button { track(job, .applied) } label: { Label("Applied", systemImage: "paperplane") }
                                    .tint(.green)
                            }
                            .swipeActions(edge: .trailing) {
                                Button { track(job, .hidden) } label: { Label("Hide", systemImage: "eye.slash") }
                                    .tint(.gray)
                                Button { track(job, .saved) } label: { Label("Save", systemImage: "bookmark") }
                                    .tint(.blue)
                            }
                        }
                    }
                }
            }
            .listStyle(.insetGrouped)
            .searchable(text: $filter.search, prompt: "Company, title, location")
            .navigationTitle("Job Radar")
            .navigationDestination(for: FeedJob.self) { JobDetailView(job: $0) }
            .refreshable { await store.refresh() }
            .overlay {
                if store.jobs.isEmpty {
                    if store.isLoading {
                        ProgressView("Loading feed…")
                    } else {
                        ContentUnavailableView(
                            "No feed yet",
                            systemImage: "dot.radiowaves.left.and.right",
                            description: Text(store.error ?? "Pull to refresh, or check the feed URL in Settings.")
                        )
                    }
                }
            }
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Menu {
                        Toggle("Hide saved, applied and hidden", isOn: $filter.hideTracked)
                        Toggle("Hide citizenship/sponsorship flags", isOn: $filter.hideWarnings)
                        Toggle("Co-ops only", isOn: $filter.onlyCoop)
                        Divider()
                        Button("Mark all as seen", systemImage: "checkmark.circle") { store.markAllSeen() }
                            .disabled(store.jobs.isEmpty)
                    } label: {
                        Label("Filters", systemImage: "line.3.horizontal.decrease.circle")
                    }
                }
            }
        }
        .onChange(of: router.openJobID) { _, id in openDeepLink(id) }
        .onChange(of: store.jobs) { _, _ in openDeepLink(router.openJobID) }
    }

    @ViewBuilder
    private func statusLine(count: Int) -> some View {
        if let error = store.error {
            Label(error, systemImage: "wifi.exclamationmark").foregroundStyle(.orange)
        } else if let at = store.generatedAt {
            Text("\(count) shown · feed updated \(at.formatted(.relative(presentation: .named)))")
        }
    }

    private func openDeepLink(_ id: String?) {
        guard let id, let job = store.job(id: id) else { return }
        path = [job]
        router.openJobID = nil
    }

    private func track(_ job: FeedJob, _ status: ApplicationStatus) {
        Tracker.set(job, status, in: context, existing: trackedByID[job.id])
    }
}

struct TierPicker: View {
    @Binding var selection: Set<String>

    var body: some View {
        HStack {
            ForEach(["A", "B", "C"], id: \.self) { tier in
                let on = selection.contains(tier)
                Button {
                    if on, selection.count > 1 { selection.remove(tier) } else { selection.insert(tier) }
                } label: {
                    Text(["A": "Core", "B": "Good", "C": "Stretch"][tier]!)
                        .font(.subheadline.weight(.medium))
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(.bordered)
                .tint(on ? .accentColor : .secondary)
                .accessibilityAddTraits(on ? .isSelected : [])
            }
        }
    }
}

enum Tracker {
    static func set(_ job: FeedJob, _ status: ApplicationStatus, in context: ModelContext, existing: TrackedJob?) {
        if let existing {
            existing.status = status
        } else {
            context.insert(TrackedJob(job: job, status: status))
        }
        try? context.save()
    }
}
