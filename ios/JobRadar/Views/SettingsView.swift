import SwiftUI

struct SettingsView: View {
    @Environment(FeedStore.self) private var store
    @Environment(\.openURL) private var openURL
    @AppStorage(Settings.Key.feedURL) private var feedURL = Settings.defaultFeedURL
    @AppStorage(Settings.Key.ntfyTopic) private var ntfyTopic = ""
    @State private var topicCopied = false
    @State private var tiers = Settings.notifyTiers
    @State private var checkResult: String?

    private var topic: String { ntfyTopic.trimmingCharacters(in: .whitespacesAndNewlines) }
    private var subscribeURL: URL? { topic.isEmpty ? nil : URL(string: "\(Settings.pushServer)/\(topic)") }

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    TextField("ntfy topic", text: $ntfyTopic)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                        .font(.body.monospaced())
                        .onChange(of: ntfyTopic) { topicCopied = false }
                    // A universal link: NTF-AI opens it as a subscribe prompt, Safari otherwise.
                    Button {
                        if let subscribeURL { openURL(subscribeURL) }
                    } label: {
                        Label("Subscribe in NTF-AI", systemImage: "bell.badge")
                    }
                    .disabled(subscribeURL == nil)
                    Button {
                        UIPasteboard.general.string = topic
                        topicCopied = true
                    } label: {
                        Label(topicCopied ? "Copied" : "Copy topic", systemImage: topicCopied ? "checkmark" : "doc.on.doc")
                    }
                    .disabled(topic.isEmpty)
                    Link("Get NTF-AI", destination: Settings.pushAppStoreURL)
                } header: {
                    Text("Instant push")
                } footer: {
                    Text("The poller pushes each new match to NTF-AI (ntf-ai.app) within minutes. Enter the topic from the repo's NTFY_TOPIC secret, tap Subscribe in NTF-AI and confirm. If Safari opens instead, copy the topic and add it in NTF-AI with + and server ntf-ai.app. Run the test-push workflow on GitHub to check.")
                }

                Section {
                    ForEach(["A", "B", "C"], id: \.self) { tier in
                        Toggle(["A": "Core fit", "B": "Good fit", "C": "Stretch"][tier]!, isOn: Binding(
                            get: { tiers.contains(tier) },
                            set: { on in
                                if on { tiers.insert(tier) } else { tiers.remove(tier) }
                                Settings.notifyTiers = tiers
                            }
                        ))
                    }
                    Button("Check for new jobs now") {
                        Task {
                            await store.refresh()
                            guard let url = Settings.feedURL, let feed = try? await FeedClient().fetch(from: url) else {
                                checkResult = store.error ?? "Could not load the feed"
                                return
                            }
                            let n = await LocalNotifier.notifyNewJobs(in: feed)
                            checkResult = n == 0 ? "No new matches" : "\(n) new matches"
                        }
                    }
                    if let checkResult { Text(checkResult).foregroundStyle(.secondary) }
                } header: {
                    Text("Backup notifications")
                } footer: {
                    Text("iOS runs background refresh when it chooses, so these can lag. ntfy is the fast path.")
                }

                Section("Feed") {
                    TextField("Feed URL", text: $feedURL, axis: .vertical)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                        .keyboardType(.URL)
                        .font(.footnote.monospaced())
                    Button("Reset to default") { feedURL = Settings.defaultFeedURL }
                    if let at = store.generatedAt {
                        LabeledContent("Last update", value: at.formatted(date: .abbreviated, time: .shortened))
                    }
                    LabeledContent("Postings", value: "\(store.jobs.count)")
                }

                Section {
                    Link("HiringCafe", destination: URL(string: "https://hiringcafe.com/?searchState=%7B%22searchQuery%22%3A%22intern%22%7D")!)
                    Link("LinkedIn internships (past 24h)", destination: URL(string: "https://www.linkedin.com/jobs/search/?keywords=software%20engineer%20intern&location=United%20States&f_TPR=r86400&f_E=1")!)
                    Link("Simplify Summer 2027 list", destination: URL(string: "https://github.com/SimplifyJobs/Summer2027-Internships")!)
                } header: {
                    Text("Browse by hand")
                } footer: {
                    Text("HiringCafe and LinkedIn don't allow automated polling. Turn on LinkedIn's own job alerts in its app.")
                }
            }
            .navigationTitle("Settings")
        }
    }
}
