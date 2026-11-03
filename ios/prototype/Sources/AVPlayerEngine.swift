import AVFoundation
import UIKit

final class AVPlayerEngine: Engine {
    let name = "avplayer"
    private let player = AVPlayer()
    private let layer = AVPlayerLayer()
    private var statusObservation: NSKeyValueObservation?
    private var failure: String?

    var positionMs: Int {
        let seconds = player.currentTime().seconds
        return seconds.isFinite ? Int(seconds * 1000) : 0
    }

    var durationMs: Int {
        let seconds = player.currentItem?.duration.seconds ?? 0
        return seconds.isFinite ? Int(seconds * 1000) : 0
    }

    var isPlaying: Bool { player.timeControlStatus == .playing }

    var lastError: String? {
        failure ?? player.currentItem?.error?.localizedDescription
    }

    var tracks: [String] {
        guard let asset = player.currentItem?.asset else { return [] }
        var described = asset.tracks.map { "\($0.mediaType.rawValue) \($0.languageCode ?? "und")" }
        for characteristic in [AVMediaCharacteristic.audible, .legible] {
            if let group = asset.mediaSelectionGroup(forMediaCharacteristic: characteristic) {
                described += group.options.map { "selectable \(characteristic.rawValue) \($0.displayName)" }
            }
        }
        return described
    }

    func attach(to view: UIView) {
        layer.player = player
        layer.frame = view.bounds
        layer.videoGravity = .resizeAspect
        view.layer.addSublayer(layer)
    }

    func layoutChanged(_ bounds: CGRect) {
        layer.frame = bounds
    }

    func open(_ media: URL, subtitle: URL?) {
        // AVPlayer has no way to add an external SRT file; recorded rather than worked around.
        if subtitle != nil { failure = "external subtitle files are not supported by AVPlayer" }
        let item = AVPlayerItem(url: media)
        statusObservation = item.observe(\.status) { [weak self] item, _ in
            if item.status == .failed { self?.failure = item.error?.localizedDescription ?? "failed" }
        }
        player.replaceCurrentItem(with: item)
    }

    func play() { player.play() }
    func pause() { player.pause() }

    func seek(toMs: Int) {
        player.seek(to: CMTime(value: CMTimeValue(toMs), timescale: 1000))
    }

    func shutDown() {
        statusObservation = nil
        player.pause()
        player.replaceCurrentItem(with: nil)
        layer.removeFromSuperlayer()
    }
}
