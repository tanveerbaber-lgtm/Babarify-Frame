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
    private val VIDEO_EXTENSIONS = setOf(
        "3g2", "3gp", "asf", "avi", "flv", "m2ts", "m4v", "mkv", "mov", "mp4", "mpeg", "mpg", "mts", "ogv", "ts",
        "vob", "webm", "wmv",
    )
    private val AUDIO_EXTENSIONS = setOf(
        "aac", "ac3", "aiff", "alac", "amr", "ape", "flac", "m4a", "mka", "mp3", "oga", "ogg", "opus", "wav", "wma",
    )

    // Same choices as the desktop app (configuration/preferences.py).
    val SPEEDS = listOf(0.5f, 0.75f, 1f, 1.25f, 1.5f, 1.75f, 2f)
    val SEEK_STEPS_S = listOf(5, 10, 15, 30, 60)
    val ASPECT_RATIOS = listOf("", "16:9", "4:3", "16:10", "21:9", "2.35:1", "1:1", "5:4")
    const val VOLUME_MIN = 1
    const val VOLUME_NORMAL_MAX = 100
    const val VOLUME_BOOST_MAX = 200
    const val MAX_DELAY_MS = 60_000L
    const val DELAY_STEP_MS = 50L
    private const val PREVIOUS_RESTARTS_AFTER_MS = 3_000L

    // ISO 639-2 keys, with the words engines put in a track's name.
    val LANGUAGES = linkedMapOf(
        "" to "No preference",
        "ara" to "Arabic",
        "chi" to "Chinese",
        "dut" to "Dutch",
        "eng" to "English",
        "fre" to "French",
        "ger" to "German",
        "hin" to "Hindi",
        "ita" to "Italian",
        "jpn" to "Japanese",
        "kor" to "Korean",
        "pol" to "Polish",
        "por" to "Portuguese",
        "rus" to "Russian",
        "spa" to "Spanish",
        "swe" to "Swedish",
        "tur" to "Turkish",
        "urd" to "Urdu",
    )
    private val LANGUAGE_ALIASES = mapOf(
        "chi" to listOf("zho", "zh"),
        "dut" to listOf("nld", "nl"),
        "eng" to listOf("en"),
        "fre" to listOf("fra", "fr"),
        "ger" to listOf("deu", "de"),
        "ara" to listOf("ar"),
        "hin" to listOf("hi"),
        "ita" to listOf("it"),
        "jpn" to listOf("ja"),
        "kor" to listOf("ko"),
        "pol" to listOf("pl"),
        "por" to listOf("pt"),
        "rus" to listOf("ru"),
        "spa" to listOf("es"),
        "swe" to listOf("sv"),
        "tur" to listOf("tr"),
        "urd" to listOf("ur"),
    )

    fun isVideoName(name: String): Boolean = name.substringAfterLast('.', "").lowercase() in VIDEO_EXTENSIONS

    fun isMediaName(name: String): Boolean {
        val extension = name.substringAfterLast('.', "").lowercase()
        return extension in VIDEO_EXTENSIONS || extension in AUDIO_EXTENSIONS
    }

    /** Normal volume is 1 to 100; only an allowed boost goes on to 200. Silence is mute's job. */
    fun volumeMaximum(allowBoost: Boolean): Int = if (allowBoost) VOLUME_BOOST_MAX else VOLUME_NORMAL_MAX

    fun clampVolume(level: Int, allowBoost: Boolean): Int = level.coerceIn(VOLUME_MIN, volumeMaximum(allowBoost))

    /** A boost is never remembered: the next session starts at 100 or less, as on desktop. */
    fun rememberedVolume(level: Int): Int = level.coerceIn(VOLUME_MIN, VOLUME_NORMAL_MAX)

    fun clampDelay(delayMs: Long): Long = delayMs.coerceIn(-MAX_DELAY_MS, MAX_DELAY_MS)

    /** Does a track's name mention this language key? An empty key never matches. */
    fun languageMatches(key: String, trackTitle: String): Boolean {
        if (key.isEmpty()) return false
        val words = trackTitle.lowercase().split(Regex("[^\\p{L}]+")).filter { it.isNotEmpty() }
        val name = LANGUAGES[key]?.lowercase()
        return key in words || (name != null && name in words) || LANGUAGE_ALIASES[key].orEmpty().any { it in words }
    }

    /** Previous goes to the start of the file first, unless it has only just begun. */
    fun previousRestartsFile(positionMs: Long, hasPrevious: Boolean): Boolean =
        !hasPrevious || positionMs > PREVIOUS_RESTARTS_AFTER_MS

    /** The chapter playing at [positionMs]: the last one that starts at or before it. */
    fun chapterIndexAt(startsMs: List<Long>, positionMs: Long): Int = startsMs.indexOfLast { it <= positionMs }

    /** Seeking back during the first seconds of a chapter goes to the one before it. */
    fun previousChapterIndex(startsMs: List<Long>, positionMs: Long): Int {
        val current = chapterIndexAt(startsMs, positionMs)
        if (current < 0) return 0
        return if (positionMs - startsMs[current] > PREVIOUS_RESTARTS_AFTER_MS) current else (current - 1).coerceAtLeast(0)
    }

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
