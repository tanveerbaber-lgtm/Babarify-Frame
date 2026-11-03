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
