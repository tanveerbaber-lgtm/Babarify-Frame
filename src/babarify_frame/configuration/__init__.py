"""User preferences: typed model and local JSON persistence (no Qt, no network)."""

from babarify_frame.configuration.preferences import (
    SCHEMA_VERSION,
    Preferences,
    PreferencesStore,
    WindowGeometry,
    default_settings_path,
)

__all__ = ["SCHEMA_VERSION", "Preferences", "PreferencesStore", "WindowGeometry", "default_settings_path"]
