import SwiftData
import SwiftUI

struct JobDetailView: View {
    let job: FeedJob
    @Environment(\.modelContext) private var context
    @Environment(\.openURL) private var openURL
    @Query private var matches: [TrackedJob]
    @State private var copied = false

    init(job: FeedJob) {
        self.job = job
        let id = job.id
        _matches = Query(filter: #Predicate<TrackedJob> { $0.jobID == id })
    }

    private var tracked: TrackedJob? { matches.first }

    var body: some View {
        List {
            Section {
                VStack(alignment: .leading, spacing: 6) {
                    HStack {
                        Text(job.company).font(.headline)
                        Spacer()
                        TierBadge(job: job)
                    }
                    Text(job.title).font(.title3.weight(.semibold))
                    Text(job.locationLine).font(.subheadline).foregroundStyle(.secondary)
                    if !job.terms.isEmpty {
                        Text(job.terms.joined(separator: ", ")).font(.subheadline).foregroundStyle(.secondary)
                    }
                }
                .padding(.vertical, 4)

                if let url = job.applyURL {
                    Button {
                        openURL(url)
                        if tracked == nil { Tracker.set(job, .saved, in: context, existing: nil) }
                    } label: {
                        Label("Open posting", systemImage: "arrow.up.right.square").frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.borderedProminent)
                }
            }

            Section("Status") {
                Picker("Status", selection: statusBinding) {
                    Text("Not tracked").tag(ApplicationStatus?.none)
                    ForEach(ApplicationStatus.allCases) { Label($0.label, systemImage: $0.symbol).tag(Optional($0)) }
                }
                if let applied = tracked?.appliedAt {
                    LabeledContent("Applied", value: applied.formatted(date: .abbreviated, time: .shortened))
                }
            }

            Section("Why it matched") {
                ForEach(job.reasons, id: \.self) { Label($0, systemImage: "checkmark.seal") }
                ForEach(job.flags, id: \.self) { flag in
                    Label(flag, systemImage: "exclamationmark.triangle").foregroundStyle(.orange)
                }
                if let sponsorship = job.sponsorship, sponsorship != "Other" {
                    LabeledContent("Sponsorship", value: sponsorship)
                }
                if !job.degrees.isEmpty {
                    LabeledContent("Degrees", value: job.degrees.joined(separator: ", "))
                }
            }

            if !job.snippet.isEmpty {
                Section("Description") {
                    Text(job.snippet).font(.callout).foregroundStyle(.secondary).textSelection(.enabled)
                }
            }

            Section("Seen on") {
                ForEach(job.sources, id: \.self) { source in
                    if let url = URL(string: source.url) {
                        Link(destination: url) { Label(source.name, systemImage: "link") }
                    }
                }
                if let posted = job.postedDate {
                    LabeledContent("Posted", value: posted.formatted(.relative(presentation: .named)))
                }
                LabeledContent("First seen", value: job.firstSeenDate.formatted(.relative(presentation: .named)))
            }

            Section {
                Button {
                    UIPasteboard.general.string = "/tailor-resume \(job.company) — \(job.title)\n\(job.url)"
                    copied = true
                } label: {
                    Label(copied ? "Copied" : "Copy /tailor-resume prompt", systemImage: copied ? "checkmark" : "doc.on.doc")
                }
                ShareLink(item: job.applyURL ?? URL(string: "https://example.com")!, subject: Text(job.title)) {
                    Label("Share posting", systemImage: "square.and.arrow.up")
                }
            } footer: {
                Text("Paste the prompt into Claude Code to build a tailored resume for this posting.")
            }
        }
        .navigationTitle(job.company)
        .navigationBarTitleDisplayMode(.inline)
    }

    private var statusBinding: Binding<ApplicationStatus?> {
        Binding(
            get: { tracked?.status },
            set: { new in
                if let new {
                    Tracker.set(job, new, in: context, existing: tracked)
                } else if let tracked {
                    context.delete(tracked)
                    try? context.save()
                }
            }
        )
    }
}
