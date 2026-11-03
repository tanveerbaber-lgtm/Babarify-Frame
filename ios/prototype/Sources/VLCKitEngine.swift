import MobileVLCKit
import UIKit

final class VLCKitEngine: NSObject, Engine, VLCMediaPlayerDelegate {
    let name = "vlckit"
    private let player = VLCMediaPlayer(options: ["--no-lua"])
    private var failure: String?

    var positionMs: Int { Int(player.time.intValue) }
    var durationMs: Int { Int(player.media?.length.intValue ?? 0) }
    var isPlaying: Bool { player.isPlaying }
    var lastError: String? { failure }

    var tracks: [String] {
        let audio = (player.audioTrackNames as? [String] ?? []).map { "audio \($0)" }
        let text = (player.videoSubTitlesNames as? [String] ?? []).map { "text \($0)" }
        return audio + text
    }

    func attach(to view: UIView) {
        player.delegate = self
        player.drawable = view
    }

    func open(_ media: URL, subtitle: URL?) {
        player.media = VLCMedia(url: media)
        if let subtitle {
            player.addPlaybackSlave(subtitle, type: .subtitle, enforce: true)
        }
    }

    func play() { player.play() }
    func pause() { player.pause() }

    func seek(toMs: Int) {
        player.time = VLCTime(int: Int32(toMs))
    }

    func shutDown() {
        player.delegate = nil
        player.stop()
        player.drawable = nil
    }

    func mediaPlayerStateChanged(_ aNotification: Notification) {
        if player.state == .error { failure = "VLCMediaPlayerState.error" }
    }
}
