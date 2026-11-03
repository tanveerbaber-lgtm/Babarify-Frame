import AVFoundation
import UIKit

/// A measurement tool, not a product. Launch arguments choose the run, for example:
/// `-engine vlckit -media h264_aac.mp4 -seekAfterMs 3000 -seekToMs 20000`.
/// Measurements go to Documents/result.json for the runner to read.
@main
final class ProbeApp: UIResponder, UIApplicationDelegate {
    var window: UIWindow?
    private var engine: Engine?
    private let video = UIView()
    private var events: [[String: Any]] = []
    private var positions: [Int] = []
    private var ticker: Timer?
    private let defaults = UserDefaults.standard

    func application(
        _ application: UIApplication,
        didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]? = nil
    ) -> Bool {
        let window = UIWindow(frame: UIScreen.main.bounds)
        let controller = UIViewController()
        controller.view.backgroundColor = .black
        video.frame = controller.view.bounds
        video.autoresizingMask = [.flexibleWidth, .flexibleHeight]
        controller.view.addSubview(video)
        window.rootViewController = controller
        window.makeKeyAndVisible()
        self.window = window

        try? AVAudioSession.sharedInstance().setCategory(.playback)
        try? AVAudioSession.sharedInstance().setActive(true)
        start()
        return true
    }

    private func start() {
        let engineName = defaults.string(forKey: "engine") ?? "avplayer"
        guard let mediaName = defaults.string(forKey: "media"),
              let media = Bundle.main.url(forResource: mediaName, withExtension: nil, subdirectory: "media")
        else {
            log("no_media", [:])
            write()
            return
        }
        let created: Engine = engineName == "vlckit" ? VLCKitEngine() : AVPlayerEngine()
        engine = created
        created.attach(to: video)
        let subtitle = defaults.string(forKey: "subtitle").flatMap {
            Bundle.main.url(forResource: $0, withExtension: nil, subdirectory: "media")
        }
        log("open", ["engine": created.name, "media": mediaName])
        created.open(media, subtitle: subtitle)
        created.play()

        let seekAfter = defaults.integer(forKey: "seekAfterMs")
        if seekAfter > 0 {
            DispatchQueue.main.asyncAfter(deadline: .now() + .milliseconds(seekAfter)) { [weak self] in
                let target = self?.defaults.integer(forKey: "seekToMs") ?? 0
                self?.log("seek", ["to_ms": target])
                self?.engine?.seek(toMs: target)
            }
        }
        let rotateAfter = defaults.integer(forKey: "rotateAfterMs")
        if rotateAfter > 0 {
            DispatchQueue.main.asyncAfter(deadline: .now() + .milliseconds(rotateAfter)) { [weak self] in
                self?.rotate()
            }
        }
        ticker = Timer.scheduledTimer(withTimeInterval: 0.5, repeats: true) { [weak self] _ in
            self?.tick()
        }
    }

    private func rotate() {
        log("rotate", ["position_ms": engine?.positionMs ?? -1])
        guard let scene = window?.windowScene else { return }
        scene.requestGeometryUpdate(.iOS(interfaceOrientations: .landscapeRight))
        window?.rootViewController?.setNeedsUpdateOfSupportedInterfaceOrientations()
        DispatchQueue.main.asyncAfter(deadline: .now() + 1) { [weak self] in
            guard let self else { return }
            (self.engine as? AVPlayerEngine)?.layoutChanged(self.video.bounds)
            self.log("rotated", ["width": self.video.bounds.width, "height": self.video.bounds.height])
        }
    }

    private func tick() {
        if let engine { positions.append(engine.positionMs) }
        write()
    }

    func applicationDidEnterBackground(_ application: UIApplication) {
        // No background playback in this prototype, matching the Android app.
        log("background", ["position_ms": engine?.positionMs ?? -1, "playing": engine?.isPlaying ?? false])
        engine?.pause()
        write()
    }

    func applicationWillEnterForeground(_ application: UIApplication) {
        log("foreground", ["position_ms": engine?.positionMs ?? -1, "playing": engine?.isPlaying ?? false])
        engine?.play()
        write()
    }

    private func log(_ name: String, _ fields: [String: Any]) {
        var event = fields
        event["event"] = name
        event["at"] = Date().timeIntervalSince1970
        events.append(event)
    }

    private func write() {
        let result: [String: Any] = [
            "engine": engine?.name ?? "none",
            "position_ms": engine?.positionMs ?? 0,
            "duration_ms": engine?.durationMs ?? 0,
            "playing": engine?.isPlaying ?? false,
            "error": engine?.lastError ?? NSNull(),
            "tracks": engine?.tracks ?? [],
            "positions_ms": positions,
            "events": events,
        ]
        guard let folder = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask).first,
              let data = try? JSONSerialization.data(withJSONObject: result, options: [.prettyPrinted])
        else { return }
        try? data.write(to: folder.appendingPathComponent("result.json"), options: .atomic)
    }
}
