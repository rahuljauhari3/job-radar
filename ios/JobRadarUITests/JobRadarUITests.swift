import XCTest

/// Drives the real app against a feed served from the host (see ios/README.md).
final class JobRadarUITests: XCTestCase {
    var app: XCUIApplication!
    let shots = ProcessInfo.processInfo.environment["JOBRADAR_SHOTS_DIR"]

    override func setUpWithError() throws {
        continueAfterFailure = false
        app = XCUIApplication()
        app.launchEnvironment["JOBRADAR_FEED_URL"] =
            ProcessInfo.processInfo.environment["JOBRADAR_FEED_URL"] ?? "http://127.0.0.1:8765/feed.json"
        addUIInterruptionMonitor(withDescription: "Notifications") { alert in
            let allow = alert.buttons["Allow"]
            if allow.exists { allow.tap(); return true }
            return false
        }
    }

    func shot(_ name: String) {
        let png = XCUIScreen.main.screenshot().pngRepresentation
        let attachment = XCTAttachment(data: png, uniformTypeIdentifier: "public.png")
        attachment.name = name
        attachment.lifetime = .keepAlways
        add(attachment)
        if let dir = shots { try? png.write(to: URL(fileURLWithPath: dir).appendingPathComponent("\(name).png")) }
    }

    func testFeedDetailApplyAndTracker() throws {
        app.launch()
        let firstRow = app.buttons.matching(identifier: "job-row").firstMatch
        XCTAssertTrue(app.staticTexts.matching(NSPredicate(format: "label CONTAINS 'shown'")).firstMatch.waitForExistence(timeout: 20))
        app.swipeUp()  // any interaction fires the notification-permission monitor
        app.swipeDown()
        shot("1-feed")

        // Filter menu
        app.buttons["Filters"].tap()
        XCTAssertTrue(app.buttons["Co-ops only"].waitForExistence(timeout: 5) || app.switches["Co-ops only"].exists)
        shot("2-filters")
        app.buttons["Co-ops only"].firstMatch.tap()
        XCTAssertTrue(app.staticTexts.matching(NSPredicate(format: "label CONTAINS[c] 'co-op'")).firstMatch.waitForExistence(timeout: 5))
        shot("3-coops")
        app.buttons["Filters"].tap()
        app.buttons["Co-ops only"].firstMatch.tap()

        // Detail
        XCTAssertTrue(firstRow.waitForExistence(timeout: 5))
        let rowLabel = firstRow.label
        firstRow.tap()
        XCTAssertTrue(app.staticTexts["Why it matched"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.buttons["Open posting"].exists)
        shot("4-detail")
        app.swipeUp()
        shot("5-detail-bottom")

        // Mark applied from the status picker
        app.swipeDown()
        app.buttons.matching(NSPredicate(format: "label BEGINSWITH 'Status'")).firstMatch.tap()
        app.buttons["Applied"].firstMatch.tap()
        XCTAssertTrue(app.staticTexts["Applied"].waitForExistence(timeout: 5))
        shot("6-applied")
        app.navigationBars.buttons.element(boundBy: 0).tap()

        // Applied posting leaves the feed (hide tracked is on) and shows in the tracker
        XCTAssertNotEqual(app.buttons.matching(identifier: "job-row").firstMatch.label, rowLabel)
        app.tabBars.buttons["Tracker"].tap()
        XCTAssertTrue(app.staticTexts.matching(NSPredicate(format: "label == '1'")).firstMatch.waitForExistence(timeout: 5))
        shot("7-tracker")

        app.tabBars.buttons["Settings"].tap()
        XCTAssertTrue(app.staticTexts["Instant push"].waitForExistence(timeout: 5) || app.otherElements["Instant push"].exists)
        shot("8-settings")
    }

    func testDeepLinkOpensJob() throws {
        guard let id = ProcessInfo.processInfo.environment["JOBRADAR_DEEPLINK_ID"] else {
            throw XCTSkip("set JOBRADAR_DEEPLINK_ID")
        }
        app.launch()
        XCTAssertTrue(app.staticTexts.matching(NSPredicate(format: "label CONTAINS 'shown'")).firstMatch.waitForExistence(timeout: 20))
        app.open(URL(string: "jobradar://job/\(id)")!)
        let springboard = XCUIApplication(bundleIdentifier: "com.apple.springboard")
        if springboard.buttons["Open"].waitForExistence(timeout: 3) { springboard.buttons["Open"].tap() }
        XCTAssertTrue(app.staticTexts["Why it matched"].waitForExistence(timeout: 8))
        shot("9-deeplink")
    }
}
