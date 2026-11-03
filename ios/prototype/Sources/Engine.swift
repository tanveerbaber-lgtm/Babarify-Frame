import UIKit

/// What the prototype needs from a playback engine. Mirrors the Android prototype's PlayerEngine.
protocol Engine: AnyObject {
    var name: String { get }
    var positionMs: Int { get }
    var durationMs: Int { get }
    var isPlaying: Bool { get }
    var lastError: String? { get }
    var tracks: [String] { get }

    func attach(to view: UIView)
    func open(_ media: URL, subtitle: URL?)
    func play()
    func pause()
    func seek(toMs: Int)
    func shutDown()
}
