package com.babarify.frame.core

/** Decisions with no Android or engine dependency, so they are tested on the JVM. */
object PlaybackRules {
    private const val RESTART_NEAR_START_MS = 5_000L
    private const val RESTART_NEAR_END_MS = 10_000L
    const val SEEK_STEP_MS = 10_000L
    // Damaged files fail at once. A healthy file can still take ~22 s (Galaxy A33) when libVLC builds
    // its font cache, on first use or after fonts change, so only a very long silence is a failure.
    const val OPEN_TIMEOUT_MS = 120_000L
    const val SHOW_PREPARING_AFTER_MS = 3_000L
    const val MAX_SUBTITLE_BYTES = 5L * 1024 * 1024
    private val SUBTITLE_EXTENSIONS = setOf("srt", "ass", "ssa", "vtt", "sub", "smi", "sami", "txt")

    /** Only `content:` addresses are opened: `file:` and web addresses from other apps are refused. */
    fun isOpenableScheme(scheme: String?): Boolean = scheme.equals("content", ignoreCase = true)

    /** Where to continue a file; the very start or end of a file restarts it. */
    fun resumePosition(positionMs: Long, durationMs: Long?, finished: Boolean): Long {
        if (finished || positionMs < RESTART_NEAR_START_MS) return 0
        if (durationMs != null && durationMs > 0 && positionMs > durationMs - RESTART_NEAR_END_MS) return 0
        return positionMs
    }

    /**
     * libVLC reports truncated and non-media files as an immediate end, not an error (M12), so an
     * end that was never preceded by progress is a file that could not be played.
     */
    fun classifyEnd(progressed: Boolean): PlaybackState =
        if (progressed) PlaybackState.ENDED else PlaybackState.ERROR

    /** The engine may also say nothing at all; never leave a blank screen waiting for it. */
    fun hasOpenTimedOut(elapsedMs: Long, progressed: Boolean, wantsToPlay: Boolean): Boolean =
        wantsToPlay && !progressed && elapsedMs >= OPEN_TIMEOUT_MS

    fun shouldShowPreparing(state: PlaybackState, elapsedMs: Long): Boolean =
        state == PlaybackState.LOADING && elapsedMs >= SHOW_PREPARING_AFTER_MS

    fun seekTarget(positionMs: Long, deltaMs: Long, durationMs: Long?): Long {
        val target = (positionMs + deltaMs).coerceAtLeast(0)
        return if (durationMs != null && durationMs > 0) target.coerceAtMost(durationMs) else target
    }

    fun formatTime(ms: Long): String {
        val total = ms.coerceAtLeast(0) / 1000
        val hours = total / 3600
        val minutes = (total % 3600) / 60
        val seconds = total % 60
        return if (hours > 0) {
            "%d:%02d:%02d".format(hours, minutes, seconds)
        } else {
            "%d:%02d".format(minutes, seconds)
        }
    }

    /** Lower-case extension if [displayName] is an acceptable subtitle file, otherwise null. */
    fun subtitleExtension(displayName: String?): String? {
        val extension = displayName?.substringAfterLast('.', "")?.lowercase() ?: return null
        return extension.takeIf { it in SUBTITLE_EXTENSIONS }
    }
}
