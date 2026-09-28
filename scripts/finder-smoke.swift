// Launch the exact bundle through the same LaunchServices path Finder uses.
// Invoked only on a native Mac by desktop.py verify --finder.
import AppKit
import Foundation

guard CommandLine.arguments.count == 3 else {
    fputs("Usage: finder-smoke.swift /absolute/app.app /absolute/private-config\n", stderr)
    exit(2)
}
let appURL = URL(fileURLWithPath: CommandLine.arguments[1])
let configuration = NSWorkspace.OpenConfiguration()
configuration.createsNewApplicationInstance = true
configuration.environment = ProcessInfo.processInfo.environment.merging(
    ["OCS_CONFIG_DIR": CommandLine.arguments[2]]) { _, new in new }
var done = false
var failed = false
NSWorkspace.shared.openApplication(at: appURL, configuration: configuration) { app, error in
    if let app = app {
        print("{\"pid\":\(app.processIdentifier)}")
    } else {
        fputs("LaunchServices failed: \(String(describing: error))\n", stderr)
        failed = true
    }
    done = true
}
let deadline = Date().addingTimeInterval(20)
while !done && Date() < deadline {
    RunLoop.current.run(until: Date().addingTimeInterval(0.1))
}
if !done || failed { exit(2) }
