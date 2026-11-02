import XCTest
@testable import JobRadar

final class FeedDecodingTests: XCTestCase {
    func fixture() throws -> Feed {
        let url = try XCTUnwrap(Bundle(for: Self.self).url(forResource: "feed_fixture", withExtension: "json"))
        return try FeedClient.decode(Data(contentsOf: url))
    }

    func testDecodesPollerFeed() throws {
        let feed = try fixture()
        XCTAssertEqual(feed.version, 1)
        XCTAssertEqual(Set(feed.jobs.map(\.tier)), ["A", "B", "C"])
        let job = try XCTUnwrap(feed.jobs.first)
        XCTAssertFalse(job.company.isEmpty)
        XCTAssertNotNil(job.applyURL)
        XCTAssertFalse(job.sources.isEmpty)
        XCTAssertGreaterThan(job.firstSeen, 1_700_000_000)
    }

    func testCachesLastGoodFeed() async throws {
        let dir = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        let source = try XCTUnwrap(Bundle(for: Self.self).url(forResource: "feed_fixture", withExtension: "json"))
        let client = FeedClient(cacheURL: dir.appendingPathComponent("feed.json"))
        XCTAssertNil(client.cached())
        let feed = try await client.fetch(from: source)  // file:// goes through URLSession too
        XCTAssertEqual(client.cached()?.jobs.count, feed.jobs.count)
    }
}

final class FilterTests: XCTestCase {
    var jobs: [FeedJob] = []

    override func setUpWithError() throws {
        jobs = try FeedDecodingTests().fixture().jobs
    }

    func testTierFilter() {
        let onlyA = FeedFilter(tiers: ["A"]).apply(jobs, tracked: [])
        XCTAssertFalse(onlyA.isEmpty)
        XCTAssertTrue(onlyA.allSatisfy { $0.tier == "A" })
    }

    func testHidesTracked() {
        let id = jobs[0].id
        XCTAssertFalse(FeedFilter().apply(jobs, tracked: [id]).contains { $0.id == id })
        XCTAssertTrue(FeedFilter(hideTracked: false).apply(jobs, tracked: [id]).contains { $0.id == id })
    }

    func testSearchMatchesAllWords() {
        let job = jobs[0]
        let words = "\(job.company.split(separator: " ")[0]) \(job.title.split(separator: " ")[0])"
        XCTAssertTrue(FeedFilter(search: words).apply(jobs, tracked: []).contains(job))
        XCTAssertTrue(FeedFilter(search: "zzzz-not-a-company").apply(jobs, tracked: []).isEmpty)
    }

    func testHideWarnings() {
        let filtered = FeedFilter(hideWarnings: true).apply(jobs, tracked: [])
        XCTAssertTrue(filtered.allSatisfy { !$0.hasWarning })
    }

    func testGroupsByDayNewestFirst() {
        let groups = FeedFilter.byDay(jobs)
        XCTAssertEqual(groups.flatMap(\.jobs).count, jobs.count)
        XCTAssertEqual(groups.map(\.day), groups.map(\.day).sorted(by: >))
    }

    func testNotifyOnlyUnseenSelectedTiers() {
        let seen: Set<String> = [jobs[0].id]
        let picks = NewJobs.toNotify(jobs, seen: seen, tiers: ["A", "B"])
        XCTAssertFalse(picks.contains { $0.id == jobs[0].id })
        XCTAssertTrue(picks.allSatisfy { ["A", "B"].contains($0.tier) })
        XCTAssertEqual(picks.map(\.score), picks.map(\.score).sorted(by: >))
    }
}

@MainActor
final class RouterTests: XCTestCase {
    func testDeepLinkOpensJob() {
        let router = Router()
        router.tab = .settings
        router.open(URL(string: "jobradar://job/abc123")!)
        XCTAssertEqual(router.tab, .feed)
        XCTAssertEqual(router.openJobID, "abc123")
        router.open(URL(string: "https://example.com/job/x")!)
        XCTAssertEqual(router.openJobID, "abc123")
    }
}
