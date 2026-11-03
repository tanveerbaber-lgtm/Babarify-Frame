package com.babarify.frame.core

// Names and meanings follow the desktop app's core/models.py and core/errors.py
// (docs/milestones/M12/shared-contracts.md).

enum class PlaybackState { READY, LOADING, PLAYING, PAUSED, ENDED, ERROR }

enum class ErrorCode {
    MEDIA_NOT_FOUND,
    MEDIA_OPEN_FAILED,
    ENGINE_FAILURE,
}

enum class TrackKind { AUDIO, SUBTITLE }

/** One selectable track; [DISABLED_ID] is the engine's "off" entry. */
data class TrackInfo(val id: Int, val kind: TrackKind, val title: String, val selected: Boolean) {
    companion object {
        const val DISABLED_ID = -1
    }
}

data class ChapterInfo(val title: String, val startMs: Long)

data class QueueItem(val uri: String, val title: String)

/** What happens when the user leaves the player without closing it. */
enum class LeaveAction { STOP, AUDIO, PICTURE }

enum class SortOrder { NAME, DATE_ADDED, RECENTLY_PLAYED, DURATION, SIZE }

/** The look of plain-text subtitles; ASS and SSA files keep their own styling, as on desktop. */
data class SubtitleStyle(val sizePct: Int = 100, val textColor: Int = 0xFFFFFF, val backgroundOpacity: Int = 0) {
    fun normalized() = SubtitleStyle(
        sizePct.coerceIn(50, 200),
        textColor and 0xFFFFFF,
        backgroundOpacity.coerceIn(0, 100),
    )
}
