"""Normalised playback errors. Engine-specific failures are mapped onto these codes."""

from __future__ import annotations

from enum import Enum


class ErrorCode(Enum):
    INVALID_STATE = "invalid_state"  # command not allowed in the current state
    INVALID_ARGUMENT = "invalid_argument"
    MEDIA_NOT_FOUND = "media_not_found"
    MEDIA_OPEN_FAILED = "media_open_failed"  # engine could not open or decode the media
    UNSUPPORTED = "unsupported"  # capability not offered by this engine
    ENGINE_UNAVAILABLE = "engine_unavailable"  # engine library missing or failed to load
    ENGINE_FAILURE = "engine_failure"  # unexpected engine error


# Short, user-facing explanations. Technical detail goes in PlaybackError.detail.
USER_MESSAGES: dict[ErrorCode, str] = {
    ErrorCode.INVALID_STATE: "That action isn't available right now.",
    ErrorCode.INVALID_ARGUMENT: "That value isn't allowed.",
    ErrorCode.MEDIA_NOT_FOUND: "The file could not be found.",
    ErrorCode.MEDIA_OPEN_FAILED: (
        "This file could not be played. It may be damaged or use an unsupported format."
    ),
    ErrorCode.UNSUPPORTED: "This feature isn't supported by the current playback engine.",
    ErrorCode.ENGINE_UNAVAILABLE: "The playback engine could not be loaded.",
    ErrorCode.ENGINE_FAILURE: "The playback engine reported an unexpected error.",
}


class PlaybackError(Exception):
    def __init__(self, code: ErrorCode, detail: str = "") -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code.value}: {detail}" if detail else code.value)

    @property
    def user_message(self) -> str:
        return USER_MESSAGES[self.code]
