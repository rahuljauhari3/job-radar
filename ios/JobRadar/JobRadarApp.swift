import BackgroundTasks
import SwiftData
import SwiftUI
import UserNotifications

@main
struct JobRadarApp: App {
    @UIApplicationDelegateAdaptor private var delegate: AppDelegate
    @State private var store = FeedStore()
    @State private var router = Router.shared
    @Environment(\.scenePhase) private var scenePhase

    var body: some Scene {
        WindowGroup {
            RootView()
                .environment(store)
                .environment(router)
                .onOpenURL { router.open($0) }
                .task {
                    await store.refresh()
                    _ = await LocalNotifier.requestPermission()
                }
        }
        .modelContainer(for: TrackedJob.self)
        .backgroundTask(.appRefresh(BackgroundRefresh.identifier)) {
            await BackgroundRefresh.run()
        }
        .onChange(of: scenePhase) { _, phase in
            if phase == .background { BackgroundRefresh.schedule() }
        }
    }
}

/// Deep links: `jobradar://job/<id>` from an ntfy push or notification, `jobradar://feed`.
@MainActor
@Observable
final class Router {
    static let shared = Router()
    var tab: Tab = .feed
    var openJobID: String?

    enum Tab: Hashable { case feed, tracker, settings }

    func open(_ url: URL) {
        guard url.scheme == "jobradar" else { return }
        tab = .feed
        if url.host == "job", let id = url.pathComponents.dropFirst().first {
            openJobID = id
        }
    }
}

final class AppDelegate: NSObject, UIApplicationDelegate, UNUserNotificationCenterDelegate {
    func application(_ application: UIApplication, didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]? = nil) -> Bool {
        UNUserNotificationCenter.current().delegate = self
        return true
    }

    func userNotificationCenter(_ center: UNUserNotificationCenter, willPresent notification: UNNotification) async -> UNNotificationPresentationOptions {
        [.banner, .list, .sound]
    }

    func userNotificationCenter(_ center: UNUserNotificationCenter, didReceive response: UNNotificationResponse) async {
        if let id = response.notification.request.content.userInfo["jobID"] as? String {
            await MainActor.run { Router.shared.open(URL(string: "jobradar://job/\(id)")!) }
        }
    }
}

struct RootView: View {
    @Environment(Router.self) private var router

    var body: some View {
        @Bindable var router = router
        TabView(selection: $router.tab) {
            FeedView()
                .tabItem { Label("Feed", systemImage: "dot.radiowaves.left.and.right") }
                .tag(Router.Tab.feed)
            TrackerView()
                .tabItem { Label("Tracker", systemImage: "list.bullet.clipboard") }
                .tag(Router.Tab.tracker)
            SettingsView()
                .tabItem { Label("Settings", systemImage: "gearshape") }
                .tag(Router.Tab.settings)
        }
    }
}
