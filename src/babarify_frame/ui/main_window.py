"""Main application shell (M3): navigation rail, page stack, menus, shortcuts, fullscreen, preferences.

Pages:
* Home — "Open file", plus Continue watching and Recently played once there is history (M6).
* Library — folders the user chose, search, sort and playlists (M6).
* Now Playing — ``PlayerPage``; owns the playback controller.
* Settings — persisted UI preferences.

Keyboard model: playback shortcuts (Space, arrows, M, S, F, the M5 track keys V, B, G, H,
J, K and the M7 keys Shift+S, period, comma, L) are active only while the Now Playing page
is shown, so they never fight with form controls elsewhere. Ctrl+O, Ctrl+Q, Ctrl+1/2/3, F1
and Esc work everywhere.
"""

from __future__ import annotations

import contextlib
import random
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import (
    QAction,
    QCloseEvent,
    QDragEnterEvent,
    QDragLeaveEvent,
    QDropEvent,
    QGuiApplication,
    QIcon,
    QKeySequence,
)
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QSizePolicy,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from babarify_frame import PRODUCT_NAME, TAGLINE, __version__
from babarify_frame.ai import models as ai_models
from babarify_frame.configuration.preferences import Preferences, PreferencesStore, WindowGeometry
from babarify_frame.core.enhancements import EqualizerSettings
from babarify_frame.core.models import SUBTITLE_EXTENSIONS, MediaInfo, PlaybackState
from babarify_frame.core.music import SLEEP_MINUTES, STYLE_LABELS, VisualStyle
from babarify_frame.core.network import is_network_uri
from babarify_frame.core.themes import THEMES
from babarify_frame.library import backup
from babarify_frame.library.database import LibraryDatabase
from babarify_frame.library.models import HistoryEntry
from babarify_frame.library.service import LibraryService
from babarify_frame.playback.controller import PlaybackController
from babarify_frame.playback.factory import EngineFactory
from babarify_frame.playback.preview import FramePreview
from babarify_frame.ui import theme
from babarify_frame.ui.ai import (
    GenerateSubtitlesDialog,
    JobResult,
    ModelDownload,
    SpokenSearchDialog,
    SubtitleJob,
    ai_installed,
    generated_size,
)
from babarify_frame.ui.audio_view import QueueDialog
from babarify_frame.ui.bookmarks import BookmarksDialog
from babarify_frame.ui.diagnostics import PlaybackInfoDialog
from babarify_frame.ui.enhancements import EnhancementsDialog
from babarify_frame.ui.media_info import MediaInfoDialog
from babarify_frame.ui.network import NetworkStreamDialog
from babarify_frame.ui.pages.home import SHORTCUTS, HomePage
from babarify_frame.ui.pages.library import HiddenFilesDialog, LibraryPage
from babarify_frame.ui.pages.player import VOLUME_STEP, PlayerPage
from babarify_frame.ui.pages.settings import SettingsPage, theme_swatch
from babarify_frame.ui.report import ReportDialog
from babarify_frame.ui.subtitles import SUBTITLE_FILTER
from babarify_frame.ui.widgets import format_time, glyph_icon

MEDIA_FILTER = (
    "Media files (*.mp4 *.m4v *.mkv *.mov *.avi *.wmv *.webm *.ts *.mts *.m2ts *.mpg *.mpeg *.vob "
    "*.ogv *.flv *.3gp *.mp3 *.m4a *.aac *.flac *.wav *.ogg *.opus *.wma *.ac3);;All files (*)"
)
MIN_SIZE = QSize(560, 400)
DEFAULT_SIZE = QSize(1180, 740)


class MainWindow(QMainWindow):
    def __init__(
        self,
        factory: EngineFactory,
        icon: QIcon,
        engine_name: str = "libvlc",
        store: PreferencesStore | None = None,
        library: LibraryService | None = None,
        preview_factory: Callable[[], FramePreview] | None = None,
    ) -> None:
        super().__init__()
        self._store = store or PreferencesStore()
        self._prefs = self._store.load()
        self._apply_colour_theme(self._prefs.colour_theme)
        # Without a service (tests, or a library that could not open) the app keeps an in-memory one.
        self.library_service = library or LibraryService(LibraryDatabase(None))
        self._was_maximized = False
        self._info_dialog: PlaybackInfoDialog | None = None
        self._enhancements: EnhancementsDialog | None = None
        self._media_info_dialog: MediaInfoDialog | None = None
        self._bookmarks_dialog: BookmarksDialog | None = None
        # Local AI (M9)
        self.subtitle_job = SubtitleJob(self)
        self.model_download = ModelDownload(self)
        self._generate_dialog: GenerateSubtitlesDialog | None = None
        self._spoken_dialog: SpokenSearchDialog | None = None
        self._job_media: str | None = None

        self.setWindowTitle(PRODUCT_NAME)
        self.setWindowIcon(icon)
        self.setMinimumSize(MIN_SIZE)
        self.setAcceptDrops(True)

        self.home = HomePage(icon)
        db = self.library_service.db
        self.player = PlayerPage(
            factory, engine_name, self._prefs, history=db, preview_factory=preview_factory
        )
        self.library = LibraryPage(self.library_service, self._prefs.library_sort)
        self.settings = SettingsPage(self._prefs, self._store.path, library_path=db.path)
        self._pages = QStackedWidget()
        for page in (self.home, self.library, self.player, self.settings):
            self._pages.addWidget(page)

        root = QWidget()
        root.setObjectName("root")
        row = QHBoxLayout(root)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        self._nav_icons: list[tuple[QToolButton, str]] = []
        self._rail = self._build_rail(icon)
        row.addWidget(self._rail)
        row.addWidget(self._pages, stretch=1)
        self.setCentralWidget(root)

        self._build_actions()
        self._connect_pages()
        self.statusBar().showMessage(f"Version {__version__} · Local-only · No telemetry")
        self._restore_geometry()
        self.statusBar().setVisible(self._prefs.show_status_bar)
        self.show_page(self.home)

    # ------------------------------------------------------------ layout
    def _build_rail(self, icon: QIcon) -> QFrame:
        rail = QFrame()
        rail.setObjectName("navRail")
        rail.setFixedWidth(100)  # the longest label, Animation, has to fit
        box = QVBoxLayout(rail)
        box.setContentsMargins(0, theme.L, 0, theme.M)
        box.setSpacing(theme.XS)
        logo = QLabel()
        logo.setPixmap(icon.pixmap(36, 36))
        logo.setAccessibleName(f"{PRODUCT_NAME} logo")
        box.addWidget(logo, alignment=Qt.AlignmentFlag.AlignHCenter)
        box.addSpacing(theme.L)
        self._nav = QButtonGroup(self)
        self._nav.setExclusive(True)
        self.nav_home = self._nav_button("home", "Home", "Home (Ctrl+1)", self.home)
        self.nav_library = self._nav_button("library", "Library", "Library (Ctrl+L)", self.library)
        self.nav_player = self._nav_button("now_playing", "Playing", "Now Playing (Ctrl+2)", self.player)
        self.nav_settings = self._nav_button("settings", "Settings", "Settings (Ctrl+3)", self.settings)
        for button in (self.nav_home, self.nav_library, self.nav_player):
            box.addWidget(button)
        box.addStretch(1)
        box.addWidget(self.nav_settings)
        self.nav_theme = self._nav_button("theme", "Theme", "Change the colour theme", None)
        self.nav_theme.setCheckable(False)
        self.nav_theme.setAccessibleName("Colour theme")
        self.nav_theme.clicked.connect(self._show_theme_menu)
        box.addWidget(self.nav_theme)
        self.nav_animation = self._nav_button("animation", "Animation", "Animation for audio", None)
        self.nav_animation.setCheckable(False)
        self.nav_animation.setAccessibleName("Animation for audio")
        self.nav_animation.clicked.connect(self._show_animation_menu)
        box.addWidget(self.nav_animation)
        return rail

    def _nav_button(self, glyph: str, text: str, tip: str, page: QWidget | None) -> QToolButton:
        button = QToolButton()
        button.setObjectName("navButton")
        button.setText(text)
        button.setToolTip(tip)
        button.setAccessibleName(text if text != "Playing" else "Now Playing")
        self._nav_icons.append((button, glyph))
        nav_icon = glyph_icon(glyph, theme.TEXT, theme.TEXT_DISABLED, size=48)
        if nav_icon is not None:
            button.setIcon(nav_icon)
            button.setIconSize(QSize(22, 22))
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        button.setCheckable(True)
        button.setFixedHeight(60)
        button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        if page is not None:
            self._nav.addButton(button)
            button.clicked.connect(lambda _=False, p=page: self.show_page(p))
        return button

    def _action(self, text: str, keys: list[QKeySequence], slot: Callable[[], object]) -> QAction:
        action = QAction(text, self)
        action.setShortcuts(keys)
        action.triggered.connect(slot)
        self.addAction(action)  # shortcuts keep working while menus and rail are hidden in fullscreen
        return action

    def _build_actions(self) -> None:
        K = QKeySequence
        p = self.player
        self.open_action = self._action("&Open file…", [K(K.StandardKey.Open)], self.choose_file)
        self.open_stream_action = self._action("Open network &stream…", [K("Ctrl+N")], self.choose_stream)
        quit_action = self._action("E&xit", [K("Ctrl+Q")], self.close)
        self.home_action = self._action("&Home", [K("Ctrl+1")], lambda: self.show_page(self.home))
        self.player_action = self._action("&Now Playing", [K("Ctrl+2")], lambda: self.show_page(self.player))
        self.settings_action = self._action("&Settings", [K("Ctrl+3")], lambda: self.show_page(self.settings))
        self.library_action = self._action("&Library", [K("Ctrl+L")], lambda: self.show_page(self.library))
        self.add_folder_action = self._action("Add folder to &library…", [], self.choose_library_folder)
        self.next_action = self._action("&Next in playlist", [K(Qt.Key.Key_N)], p.next_in_queue)
        self.previous_action = self._action("P&revious in playlist", [K(Qt.Key.Key_P)], p.previous_in_queue)
        self.start_over_action = self._action("Start &over", [K(Qt.Key.Key_Home)], p.start_over)
        self.shuffle_action = self._action("S&huffle", [K(Qt.Key.Key_Z)], p.toggle_shuffle)
        self.repeat_action = self._action("&Repeat: off, this file, all", [K(Qt.Key.Key_R)], p.cycle_repeat)
        self.queue_action = self._action("&Queue…", [K(Qt.Key.Key_Q)], self.show_queue)
        self.favourite_action = self._action(
            "Add to or remove from fa&vourites", [K(Qt.Key.Key_U)], p.toggle_favourite
        )
        # Playback actions: enabled only on the Now Playing page (see module docstring).
        self.play_action = self._action(
            "&Play/Pause", [K(Qt.Key.Key_Space), K(Qt.Key.Key_MediaTogglePlayPause)], p.toggle_play_pause
        )
        self.stop_action = self._action("&Stop", [K(Qt.Key.Key_S), K(Qt.Key.Key_MediaStop)], p.stop)
        self.back_action = self._action("Seek &back", [K(Qt.Key.Key_Left)], lambda: p.seek_step(-1))
        self.forward_action = self._action("Seek &forward", [K(Qt.Key.Key_Right)], lambda: p.seek_step(1))
        self.volume_up_action = self._action(
            "Volume &up", [K(Qt.Key.Key_Up)], lambda: p.step_volume(VOLUME_STEP)
        )
        self.volume_down_action = self._action(
            "Volume &down", [K(Qt.Key.Key_Down)], lambda: p.step_volume(-VOLUME_STEP)
        )
        self.mute_action = self._action("&Mute", [K(Qt.Key.Key_M)], p.toggle_mute)
        self.fullscreen_action = self._action(
            "&Fullscreen", [K(Qt.Key.Key_F), K(Qt.Key.Key_F11)], self.toggle_fullscreen
        )
        self._action("Exit fullscreen", [K(Qt.Key.Key_Escape)], self.exit_fullscreen)
        shortcuts_action = self._action("&Keyboard shortcuts", [K(Qt.Key.Key_F1)], self._show_shortcuts)
        self.info_action = self._action("Playback &info…", [K("Ctrl+I")], self.show_playback_info)
        # Audio and subtitles (M5)
        self.load_subtitle_action = self._action(
            "Load &subtitle file…", [K("Ctrl+Shift+O")], self.choose_subtitle_file
        )
        self.next_subtitle_action = self._action("Next su&btitle track", [K(Qt.Key.Key_V)], p.cycle_subtitles)
        self.next_audio_action = self._action("Next &audio track", [K(Qt.Key.Key_B)], p.cycle_audio)
        self.subtitle_earlier_action = self._action(
            "Subtitles 50 ms earlier", [K(Qt.Key.Key_G)], lambda: p.step_subtitle_delay(-1)
        )
        self.subtitle_later_action = self._action(
            "Subtitles 50 ms later", [K(Qt.Key.Key_H)], lambda: p.step_subtitle_delay(1)
        )
        self.audio_earlier_action = self._action(
            "Audio 50 ms earlier", [K(Qt.Key.Key_J)], lambda: p.step_audio_delay(-1)
        )
        self.audio_later_action = self._action(
            "Audio 50 ms later", [K(Qt.Key.Key_K)], lambda: p.step_audio_delay(1)
        )
        self.sync_action = self._action("Sync and &delay…", [K("Ctrl+D")], p.show_sync_dialog)
        # Picture and sound (M7)
        self.enhancements_action = self._action("&Picture && Sound…", [K("Ctrl+E")], self.show_enhancements)
        self.snapshot_action = self._action("Take &snapshot", [K("Shift+S")], lambda: p.take_snapshot())
        self.next_frame_action = self._action("Next &frame", [K(Qt.Key.Key_Period)], lambda: p.frame_step())
        self.previous_frame_action = self._action(
            "Pre&vious frame", [K(Qt.Key.Key_Comma)], lambda: p.frame_step(backward=True)
        )
        self.ab_action = self._action("&A-B repeat", [K(Qt.Key.Key_L)], p.ab_loop_step)
        # Advanced media (M8)
        self.next_chapter_action = self._action("Next c&hapter", [K("Ctrl+Right")], p.next_chapter)
        self.previous_chapter_action = self._action("Previous chap&ter", [K("Ctrl+Left")], p.previous_chapter)
        self.add_bookmark_action = self._action("Add &bookmark", [K("Ctrl+B")], lambda: p.add_bookmark())
        self.bookmarks_action = self._action("Boo&kmarks…", [K("Ctrl+Shift+B")], self.show_bookmarks)
        self.generate_subtitles_action = self._action(
            "&Generate subtitles (local AI)…", [K("Ctrl+Shift+G")], self.show_generate_subtitles
        )
        self.spoken_search_action = self._action(
            "Search &spoken words…", [K("Ctrl+Shift+F")], self.show_spoken_search
        )
        self.media_info_action = self._action(
            "&Media information…", [K("Ctrl+Shift+I")], self.show_media_info
        )
        self._track_actions = (
            self.next_subtitle_action,
            self.next_audio_action,
            self.subtitle_earlier_action,
            self.subtitle_later_action,
            self.audio_earlier_action,
            self.audio_later_action,
        )
        self.report_action = self._action("&Report a problem…", [], self.show_report)
        about_action = QAction(f"&About {PRODUCT_NAME}", self)
        about_action.triggered.connect(self._show_about)
        self._playback_actions = (
            self.play_action,
            self.stop_action,
            self.back_action,
            self.forward_action,
            self.volume_up_action,
            self.volume_down_action,
            self.mute_action,
            self.fullscreen_action,
        )

        menus = self.menuBar()
        file_menu = menus.addMenu("&File")
        file_menu.addAction(self.open_action)
        file_menu.addAction(self.open_stream_action)
        file_menu.addAction(self.load_subtitle_action)
        file_menu.addAction(self.add_folder_action)
        file_menu.addSeparator()
        file_menu.addAction(quit_action)
        play_menu = menus.addMenu("&Playback")
        for action in self._playback_actions[:4]:
            play_menu.addAction(action)
        play_menu.addAction(self.start_over_action)
        play_menu.addSeparator()
        play_menu.addAction(self.next_chapter_action)
        play_menu.addAction(self.previous_chapter_action)
        self.chapters_menu = play_menu.addMenu("&Chapters")
        self.chapters_menu.aboutToShow.connect(self._fill_chapters_menu)
        play_menu.addAction(self.add_bookmark_action)
        play_menu.addAction(self.bookmarks_action)
        play_menu.addSeparator()
        play_menu.addAction(self.next_action)
        play_menu.addAction(self.previous_action)
        play_menu.addAction(self.shuffle_action)
        play_menu.addAction(self.repeat_action)
        play_menu.addAction(self.queue_action)
        play_menu.addAction(self.favourite_action)
        self.sleep_menu = play_menu.addMenu("S&leep timer")
        self.sleep_menu.aboutToShow.connect(self._fill_sleep_menu)
        play_menu.addSeparator()
        for action in (self.volume_up_action, self.volume_down_action, self.mute_action):
            play_menu.addAction(action)
        tracks_menu = menus.addMenu("&Audio && Subtitles")
        tracks_menu.addAction(self.next_audio_action)
        tracks_menu.addAction(self.next_subtitle_action)
        tracks_menu.addAction(self.load_subtitle_action)
        tracks_menu.addSeparator()
        for action in self._track_actions[2:]:
            tracks_menu.addAction(action)
        tracks_menu.addAction(self.sync_action)
        tracks_menu.addSeparator()
        tracks_menu.addAction(self.generate_subtitles_action)
        video_menu = menus.addMenu("Vi&deo")
        video_menu.addAction(self.enhancements_action)
        video_menu.addSeparator()
        for action in (
            self.snapshot_action,
            self.next_frame_action,
            self.previous_frame_action,
            self.ab_action,
        ):
            video_menu.addAction(action)
        view_menu = menus.addMenu("&View")
        for action in (self.home_action, self.library_action, self.player_action, self.settings_action):
            view_menu.addAction(action)
        view_menu.addSeparator()
        view_menu.addAction(self.fullscreen_action)
        view_menu.addAction(self.info_action)
        view_menu.addAction(self.media_info_action)
        view_menu.addAction(self.spoken_search_action)
        self.status_bar_action = QAction("Status &bar", self)
        self.status_bar_action.setCheckable(True)
        self.status_bar_action.setChecked(self._prefs.show_status_bar)
        self.status_bar_action.toggled.connect(self._choose_status_bar)
        view_menu.addAction(self.status_bar_action)
        self.animation_menu = view_menu.addMenu("&Animation for audio")
        self.animation_menu.aboutToShow.connect(self._fill_animation_menu)
        help_menu = menus.addMenu("&Help")
        help_menu.addAction(shortcuts_action)
        help_menu.addAction(self.report_action)
        help_menu.addAction(about_action)

    def _connect_pages(self) -> None:
        self.home.open_requested.connect(self.choose_file)
        self.player.open_requested.connect(self.choose_file)
        self.player.subtitle_file_requested.connect(self.choose_subtitle_file)
        self.player.fullscreen_requested.connect(self.toggle_fullscreen)
        self.player.status_changed.connect(self.statusBar().showMessage)
        self.player.title_changed.connect(self._set_media_title)
        self.player.state_changed.connect(lambda _state: self._update_actions())
        self.player.queue_changed.connect(self._update_actions)
        self.player.queue_requested.connect(self.show_queue)
        self.player.repeat_changed.connect(self._on_repeat_changed)
        self.player.engine_ready.connect(self._on_engine_ready)
        self.player.video_started.connect(self._on_video_started)
        self.settings.preferences_changed.connect(self._on_preferences_changed)
        # Library and history (M6)
        self.settings.clear_history_requested.connect(self.clear_history)
        self.settings.hidden_files_requested.connect(self.show_hidden_files)
        self.settings.backup_requested.connect(self.back_up)
        self.settings.restore_requested.connect(self.restore_from_backup)
        self.library.play_requested.connect(self.open_path)
        self.library.play_list_requested.connect(self.play_list)
        self.library.shuffle_requested.connect(self.shuffle_list)
        self.library.play_next_requested.connect(self.player.play_next)
        self.library.add_to_queue_requested.connect(self.player.add_to_queue)
        self.player.favourites_changed.connect(self.library.refresh_current_tab)
        self.library.status_changed.connect(self.statusBar().showMessage)
        self.library.sort_changed.connect(self._on_library_sort)
        self.home.play_requested.connect(self.open_path)
        self.home.forget_requested.connect(self._forget)
        self.player.history_changed.connect(self._history_changed)
        self.player.bookmarks_changed.connect(self._refresh_bookmarks)
        self.settings.download_model_requested.connect(self.download_model)
        self.settings.delete_model_requested.connect(self.delete_model)
        self.settings.delete_generated_requested.connect(self.delete_generated_subtitles)
        self.subtitle_job.stage.connect(self._job_stage)
        self.subtitle_job.progress.connect(self._job_progress)
        self.subtitle_job.finished.connect(self._job_finished)
        self.model_download.message.connect(lambda text: self._refresh_ai_status(busy=text))
        self.model_download.finished.connect(self._download_finished)
        self.player.media_info_changed.connect(self._refresh_media_info)
        self.player.media_info_changed.connect(self._update_actions)
        self.player.picture_changed.connect(lambda v: self._remember(picture=v))
        self.player.equalizer_changed.connect(lambda v: self._remember(equalizer=v))
        self.player.enhancements_reset.connect(self._refresh_enhancements)
        self.player.state_changed.connect(lambda _s: self._refresh_enhancements())
        self.player.state_changed.connect(
            lambda state: self.library_service.set_playback_active(state is PlaybackState.PLAYING)
        )
        self._home_dirty = True
        self._update_actions()

    # --------------------------------------------------------- navigation
    @property
    def controller(self) -> PlaybackController:
        return self.player.controller

    def start_engine(self) -> None:
        self.player.start_engine()
        db = self.library_service.db
        if db.folders():
            self.library.rescan()  # background: picks up new, changed and missing files

    def current_page(self) -> QWidget:
        page = self._pages.currentWidget()
        assert page is not None
        return page

    def show_page(self, page: QWidget) -> None:
        if page is not self.player and self.isFullScreen():
            self.exit_fullscreen()
        self._pages.setCurrentWidget(page)
        for button, target in (
            (self.nav_home, self.home),
            (self.nav_library, self.library),
            (self.nav_player, self.player),
            (self.nav_settings, self.settings),
        ):
            button.setChecked(target is page)
        if page is self.player:
            self.player.setFocus()
        elif page is self.home and self._home_dirty:
            self.refresh_home()
        elif page is self.library:
            self.library.refresh()
        elif page is self.settings:
            self._refresh_ai_status()
        self._update_actions()

    def _update_actions(self) -> None:
        p = self.player
        on_player = self.current_page() is self.player
        ready = p.engine_is_ready
        self.open_action.setEnabled(ready)
        self.home.set_engine_ready(ready)
        self.play_action.setEnabled(on_player and p.has_media and p.state is not PlaybackState.ERROR)
        self.stop_action.setEnabled(on_player and (p.has_media or p.state is PlaybackState.ERROR))
        self.back_action.setEnabled(on_player and p.is_seekable)
        self.forward_action.setEnabled(on_player and p.is_seekable)
        for action in (self.volume_up_action, self.volume_down_action, self.mute_action):
            action.setEnabled(on_player and ready)
        self.fullscreen_action.setEnabled(on_player)
        queue, _index = p.queue
        self.next_action.setEnabled(on_player and p.can_go_next)
        self.previous_action.setEnabled(on_player and p.can_go_previous)
        self.shuffle_action.setEnabled(on_player and len(queue) > 1)
        self.repeat_action.setEnabled(on_player)
        self.queue_action.setEnabled(on_player and len(queue) > 1)
        self.favourite_action.setEnabled(on_player and p.has_media)
        self.start_over_action.setEnabled(on_player and p.is_seekable)
        caps = p.capabilities_or_none()
        playing_video = p.has_media and p.state in (PlaybackState.PLAYING, PlaybackState.PAUSED)
        self.snapshot_action.setEnabled(on_player and playing_video and bool(caps and caps.supports_snapshot))
        self.next_frame_action.setEnabled(
            on_player and playing_video and bool(caps and caps.supports_frame_step)
        )
        self.previous_frame_action.setEnabled(
            on_player and playing_video and bool(caps and caps.supports_frame_back_step)
        )
        self.ab_action.setEnabled(on_player and p.is_seekable)
        self.load_subtitle_action.setEnabled(p.can_load_subtitles)
        for action in self._track_actions:
            action.setEnabled(on_player and p.can_change_tracks)
        self.sync_action.setEnabled(p.has_media and p.state is not PlaybackState.ERROR)
        self.open_stream_action.setEnabled(ready)
        has_chapters = on_player and p.is_seekable and len(p.chapters) > 1
        for action in (self.next_chapter_action, self.previous_chapter_action):
            action.setEnabled(has_chapters)
        self.chapters_menu.setEnabled(has_chapters)
        self.add_bookmark_action.setEnabled(on_player and p.can_bookmark)
        self.bookmarks_action.setEnabled(p.has_media)
        self.media_info_action.setEnabled(ready)
        ai_on = self._prefs.ai_enabled and ai_installed()
        uri = p.current_uri
        local_media = uri is not None and "://" not in uri
        self.generate_subtitles_action.setEnabled(ai_on and local_media)
        self.generate_subtitles_action.setVisible(ai_on)
        self.spoken_search_action.setEnabled(ai_on)
        self.spoken_search_action.setVisible(ai_on)

    # ---------------------------------------------------------- commands
    def choose_file(self) -> None:
        if not self.player.engine_is_ready:
            return
        path, _ = QFileDialog.getOpenFileName(self, "Open media", "", MEDIA_FILTER)
        if path:
            self.open_path(path)

    def open_path(self, path: str) -> None:
        self.show_page(self.player)
        self.player.open_path(path)

    def choose_stream(self) -> NetworkStreamDialog | None:
        """Ask for a network address (M8). Returns the dialog (tests drive it); opens on accept."""
        if not self.player.engine_is_ready:
            return None
        caps = self.player.capabilities_or_none()
        recent = []
        if self._prefs.remember_history:
            recent = [e.path for e in self.library_service.db.recent(50) if is_network_uri(e.path)][:8]
        dialog = NetworkStreamDialog(caps.network_schemes if caps else frozenset(), recent, self)
        dialog.accepted.connect(lambda: self.open_path(dialog.url) if dialog.url else None)
        dialog.open()
        return dialog

    # ------------------------------------------- chapters, bookmarks, info (M8)
    def _fill_chapters_menu(self) -> None:
        menu = self.chapters_menu
        menu.clear()
        current = self.player.current_chapter()
        for chapter in self.player.chapters[:200]:
            label = f"{format_time(chapter.start_ms)}  {chapter.label}".replace("&", "&&")
            action = menu.addAction(label)
            action.setCheckable(True)
            action.setChecked(current is not None and chapter.index == current.index)
            action.triggered.connect(lambda _=False, i=chapter.index: self.player.jump_to_chapter(i))

    def show_bookmarks(self) -> BookmarksDialog:
        if self._bookmarks_dialog is None:
            dialog = BookmarksDialog(self)
            dialog.jump_requested.connect(self.player.seek_to)
            dialog.add_requested.connect(lambda: self.player.add_bookmark())
            dialog.rename_requested.connect(self.player.rename_bookmark)
            dialog.delete_requested.connect(self.player.delete_bookmark)
            self._bookmarks_dialog = dialog
        self._refresh_bookmarks()
        self._bookmarks_dialog.show()
        self._bookmarks_dialog.raise_()
        return self._bookmarks_dialog

    def _refresh_bookmarks(self) -> None:
        if self._bookmarks_dialog is not None:
            p = self.player
            name = p.controls.title_label.toolTip() if p.has_media else ""
            self._bookmarks_dialog.set_bookmarks(name, p.bookmarks, can_add=p.can_bookmark)
        self._update_actions()

    # ----------------------------------------------------------- local AI (M9)
    def show_generate_subtitles(self) -> GenerateSubtitlesDialog | None:
        p = self.player
        uri = p.current_uri
        if not (self._prefs.ai_enabled and ai_installed()) or uri is None or "://" in uri:
            return None
        if self._generate_dialog is None:
            dialog = GenerateSubtitlesDialog(self)
            dialog.start_requested.connect(self._start_subtitle_job)
            dialog.cancel_requested.connect(self.subtitle_job.cancel)
            dialog.load_existing_requested.connect(self._load_existing_subtitles)
            dialog.settings_requested.connect(dialog.close)
            dialog.settings_requested.connect(lambda: self.show_page(self.settings))
            self._generate_dialog = dialog
        dialog = self._generate_dialog
        if not self.subtitle_job.running:
            dialog.prepare(
                p.media_name,
                p.controller.status().duration_ms,
                ai_models.installed_models(),
                self._prefs.ai_model,
                self._prefs.ai_language,
                self.library_service.db.transcript_for(uri),
            )
        dialog.show()
        dialog.raise_()
        return dialog

    def _start_subtitle_job(self, model: str, language: str) -> None:
        uri = self.player.current_uri
        if uri is None or self.subtitle_job.running:
            return
        self._remember(ai_model=model, ai_language=language)
        self._job_media = uri
        self.subtitle_job.start(uri, model, language)
        self.statusBar().showMessage("Generating subtitles on this PC…")

    def _job_stage(self, stage: str) -> None:
        if self._generate_dialog is not None:
            self._generate_dialog.show_stage(stage)

    def _job_progress(self, fraction: float) -> None:
        if self._generate_dialog is not None:
            self._generate_dialog.show_progress(fraction)

    def _job_finished(self, result: object, error: str) -> None:
        media, self._job_media = self._job_media, None
        dialog = self._generate_dialog
        if not isinstance(result, JobResult) or media is None:
            text = "Stopped." if error == "cancelled" else f"Subtitles could not be generated: {error}"
            if dialog is not None:
                dialog.show_result(text)
            self.statusBar().showMessage(text)
            return
        if not result.cues:
            text = "No speech was found in this file."
            if dialog is not None:
                dialog.show_result(text)
            self.statusBar().showMessage(text)
            return
        name = Path(media).name
        previous = self.library_service.db.transcript_for(media)
        if previous is not None and Path(previous.srt_path) != result.srt:
            Path(previous.srt_path).unlink(missing_ok=True)  # replaced: keep no orphan files
        self.library_service.db.save_transcript(
            media, name, str(result.srt), result.language, result.model, [(a, t) for a, _b, t in result.cues]
        )
        language = ai_models.SPEECH_LANGUAGES.get(result.language, result.language)
        text = f"Done: {len(result.cues)} lines in {language} (machine-generated)."
        if self.player.current_uri == media and self.player.can_load_subtitles:
            self.player.load_subtitle_file(str(result.srt))
            text += " Added to the subtitle tracks."
        if dialog is not None:
            dialog.show_progress(1.0)
            dialog.show_result(text)
        self.statusBar().showMessage(text)
        self._refresh_ai_status()

    def _load_existing_subtitles(self) -> None:
        uri = self.player.current_uri
        transcript = self.library_service.db.transcript_for(uri) if uri else None
        if transcript is not None and Path(transcript.srt_path).is_file() and self.player.can_load_subtitles:
            self.player.load_subtitle_file(transcript.srt_path)
            if self._generate_dialog is not None:
                self._generate_dialog.show_result("Loaded the machine-generated subtitles.")

    def show_spoken_search(self) -> SpokenSearchDialog | None:
        if not self._prefs.ai_enabled:
            return None
        if self._spoken_dialog is None:
            dialog = SpokenSearchDialog(self.library_service.db.search_spoken, self)
            dialog.open_requested.connect(self._open_spoken_hit)
            self._spoken_dialog = dialog
        self._spoken_dialog.show()
        self._spoken_dialog.raise_()
        return self._spoken_dialog

    def _open_spoken_hit(self, path: str, position_ms: int) -> None:
        self.show_page(self.player)
        self.player.open_at(path, max(0, position_ms - 1000))  # a moment before the words

    def download_model(self, name: str) -> None:
        model = ai_models.MODELS.get(name)
        if model is None or self.model_download.running:
            return
        answer = QMessageBox.question(
            self,
            "Download speech model",
            f"Download the {model.label} speech model ({model.size / 1e6:.0f} MB) from "
            f"{model.source} (revision {model.revision[:10]})?\n\nLicence: {ai_models.LICENCE}.\n"
            "Only the model is downloaded; nothing about you or your media is sent. Files are "
            "checked against known checksums before use.",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.model_download.start(name)
        self._refresh_ai_status(busy="Downloading…")

    def _download_finished(self, name: str, error: str) -> None:
        model = ai_models.MODELS[name]
        text = f"{model.label} model installed" if not error else f"Download failed: {error}"
        self.statusBar().showMessage(text)
        self._refresh_ai_status()
        if self._generate_dialog is not None and self._generate_dialog.isVisible():
            self.show_generate_subtitles()

    def delete_model(self, name: str) -> None:
        model = ai_models.MODELS.get(name)
        if model is None or self.subtitle_job.running:
            return
        answer = QMessageBox.question(
            self, "Delete speech model", f"Delete the {model.label} model ({model.size / 1e6:.0f} MB)?"
        )
        if answer == QMessageBox.StandardButton.Yes:
            ai_models.delete(name)
            self._refresh_ai_status()

    def delete_generated_subtitles(self) -> None:
        db = self.library_service.db
        count = len(db.transcripts())
        answer = QMessageBox.question(
            self,
            "Delete generated subtitles",
            f"Delete all {count} machine-generated subtitle files and their search index? Your media "
            "files and other subtitles are not affected.",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        for transcript in db.delete_all_transcripts():
            srt = Path(transcript.srt_path)
            srt.unlink(missing_ok=True)
            with contextlib.suppress(OSError):
                srt.parent.rmdir()  # the per-file folder, if now empty
        self.statusBar().showMessage("Generated subtitles deleted")
        self._refresh_ai_status()

    def _refresh_ai_status(self, busy: str = "") -> None:
        transcripts = self.library_service.db.transcripts()
        statuses = {name: ai_models.status(name) for name in ai_models.MODELS}
        if self.model_download.running and not busy:
            busy = "Downloading…"
        self.settings.set_ai_status(
            statuses, len(transcripts), generated_size(transcripts), busy, installed=ai_installed()
        )

    def show_report(self) -> ReportDialog:
        """Help → Report a problem (M11): text to copy into the issue form; nothing is sent."""

        def gather() -> tuple[dict[str, str], MediaInfo | None, str, str]:
            p = self.player
            if not p.engine_is_ready:
                return {"Engine": "not started"}, None, "", p.last_error
            diag = dict(p.controller.engine.diagnostics())
            diag.pop("log_errors", None)
            info = p.controller.media_info() if p.has_media else None
            return diag, info, p.media_name, p.last_error

        dialog = ReportDialog(gather, self)
        dialog.show()
        return dialog

    def show_media_info(self) -> MediaInfoDialog:
        if self._media_info_dialog is None:
            self._media_info_dialog = MediaInfoDialog(self)
        self._refresh_media_info()
        self._media_info_dialog.show()
        self._media_info_dialog.raise_()
        return self._media_info_dialog

    def _refresh_media_info(self) -> None:
        dialog = self._media_info_dialog
        if dialog is None:
            return
        p = self.player
        status = p.controller.status() if p.engine_is_ready else None
        uri = status.uri if status is not None and p.has_media and status.uri else ""
        dialog.set_media(p.controller.media_info() if uri else None, uri)

    def play_list(self, paths: list[str], start: int = 0) -> None:
        self.show_page(self.player)
        self.player.play_queue(paths, start)

    def choose_library_folder(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Add a folder to the library")
        if path:
            self.add_library_folder(path)

    def add_library_folder(self, path: str) -> None:
        self.show_page(self.library)
        self.library.add_folder(path)

    # ------------------------------------------------------- history (M6)
    def refresh_home(self) -> None:
        self._home_dirty = False
        db = self.library_service.db
        if not self._prefs.remember_history:
            self.home.set_history([], [], lambda _e: None)
            return
        self.home.set_history(db.continue_watching(), db.recent(), self._thumbnail_for)

    def _thumbnail_for(self, entry: HistoryEntry) -> Path | None:
        return self.library_service.thumbnail_path(entry.thumbnail)

    def _history_changed(self) -> None:
        self._home_dirty = True
        if self.current_page() is self.home:
            self.refresh_home()
        self._update_actions()

    def _forget(self, path: str) -> None:
        self.library_service.db.remove_history(path)
        self.refresh_home()
        self.statusBar().showMessage("Removed from history")

    def back_up(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Back up settings and playlists", "babarify-backup.json", "Backup (*.json)"
        )
        if not path:
            return
        try:
            backup.write_backup(Path(path), backup.build_backup(self._prefs, self.library_service.db))
        except OSError as exc:
            QMessageBox.warning(self, "Back up", f"The backup couldn't be saved.\n{exc}")
            return
        self._notify_status("Backup saved")

    def restore_from_backup(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Restore from a backup", "", "Backup (*.json)")
        if not path:
            return
        try:
            data = backup.read_backup(Path(path))
        except backup.BackupError as exc:
            QMessageBox.warning(self, "Restore", str(exc))
            return
        answer = QMessageBox.question(
            self,
            "Restore",
            "Your settings are replaced by the ones in the file. Playlists, favourites and hidden files are "
            "added to the ones you have.",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        restored = backup.restore_lists(data, self.library_service.db)
        prefs = Preferences.from_dict(data.get("preferences", {}))
        self.settings.set_preferences(prefs)
        self._on_preferences_changed(prefs)
        self._prefs = replace(
            self._prefs,
            repeat_mode=prefs.repeat_mode,
            library_sort=prefs.library_sort,
            picture=prefs.picture,
            equalizer=prefs.equalizer,
            profiles=prefs.profiles,
        )
        self.player.set_preferences(self._prefs)
        self._store.save(self._prefs)
        self.library.playlists.refresh()
        self.library.refresh()
        self._notify_status(
            f"Restored. New playlists: {restored.playlists}. New favourites: {restored.favourites}."
        )

    def _notify_status(self, text: str) -> None:
        QMessageBox.information(self, "Backup", text)

    def show_hidden_files(self) -> None:
        HiddenFilesDialog(self.library_service, self).exec()
        self.library.refresh()

    def clear_history(self) -> None:
        answer = QMessageBox.question(
            self,
            "Clear history",
            "Clear recently played files and all resume positions? Library folders, files and "
            "playlists are not affected.",
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.library_service.db.clear_history()
            self.refresh_home()
            self.statusBar().showMessage("History cleared")

    # ------------------------------------------------- picture and sound (M7)
    def show_enhancements(self) -> EnhancementsDialog:
        if self._enhancements is None:
            dialog = EnhancementsDialog(self._preset_values, self)
            dialog.picture_changed.connect(self.player.set_picture)
            dialog.equalizer_changed.connect(self.player.set_equalizer)
            dialog.geometry_changed.connect(self.player.set_geometry)
            dialog.transform_changed.connect(self.player.set_transform)
            dialog.profiles_changed.connect(lambda profiles: self._remember(profiles=tuple(profiles)))
            self._enhancements = dialog
        self._enhancements.set_profiles(self._prefs.profiles)
        self._refresh_enhancements()
        self._enhancements.show()
        self._enhancements.raise_()
        return self._enhancements

    def _preset_values(self, name: str) -> EqualizerSettings:
        return self.player.controller.engine.equalizer_preset(name)

    def _refresh_enhancements(self) -> None:
        dialog = self._enhancements
        if dialog is None:
            return
        p = self.player
        info = p.controller.media_info() if p.engine_is_ready else None
        has_video = bool(info and info.video_codec)
        dialog.set_capabilities(p.capabilities_or_none(), has_video)
        dialog.set_picture(self._prefs.picture)
        dialog.set_equalizer(self._prefs.equalizer)
        dialog.set_video(p.video_geometry, p.transform)

    def _remember(self, **changes: object) -> None:
        self._prefs = replace(self._prefs, **changes)  # type: ignore[arg-type]
        self._store.save(self._prefs)

    def _on_library_sort(self, sort: str) -> None:
        self._prefs = replace(self._prefs, library_sort=sort)
        self._store.save(self._prefs)

    def choose_subtitle_file(self) -> None:
        """Explicit user action: the file is read locally by the engine, never uploaded."""
        if not self.player.can_load_subtitles:
            return
        status = self.player.controller.status()
        start = str(Path(status.uri).parent) if status.uri and "://" not in status.uri else ""
        path, _ = QFileDialog.getOpenFileName(self, "Load subtitle file", start, SUBTITLE_FILTER)
        if path:
            self.player.load_subtitle_file(path)

    def _set_media_title(self, name: str) -> None:
        self.setWindowTitle(f"{name} — {PRODUCT_NAME}" if name else PRODUCT_NAME)

    def _on_engine_ready(self, ok: bool) -> None:
        # Songs waiting to be read, like an existing library's after an update, need no rescan.
        if ok and self.library_service.db.counts()[2]:
            self.library_service.fetch_metadata()
        if not ok:
            self.show_page(self.player)  # the player page explains what failed
        db = self.library_service.db
        notice = db.recovered or db.read_only_reason
        if notice:  # after the engine's own status line, so it is not overwritten
            self.statusBar().showMessage(notice)
            # Too important to leave on a bar that may be hidden: the library was replaced or not opened.
            box = QMessageBox(QMessageBox.Icon.Warning, "Library", notice, parent=self)
            box.setTextFormat(Qt.TextFormat.PlainText)
            box.open()
        self._update_actions()

    def _on_video_started(self) -> None:
        if self._prefs.start_fullscreen and not self.isFullScreen():
            self.toggle_fullscreen()

    # --------------------------------------------------------- fullscreen
    def toggle_fullscreen(self) -> None:
        if self.isFullScreen():
            self.exit_fullscreen()
            return
        if self.current_page() is not self.player:
            self.show_page(self.player)
        self._was_maximized = self.isMaximized()
        for widget in (self._rail, self.menuBar(), self.statusBar()):
            widget.hide()
        self.showFullScreen()
        self.player.set_fullscreen_mode(True)

    def exit_fullscreen(self) -> None:
        if not self.isFullScreen():
            return
        self.player.set_fullscreen_mode(False)
        if self._was_maximized:
            self.showMaximized()
        else:
            self.showNormal()
        for widget in (self._rail, self.menuBar()):
            widget.show()
        self.statusBar().setVisible(self._prefs.show_status_bar)

    # -------------------------------------------------------- preferences
    def _restore_geometry(self) -> None:
        geo = self._prefs.window
        self.resize(DEFAULT_SIZE)
        if geo is None:
            return
        rect = QRect(geo.x, geo.y, geo.width, geo.height)
        # Ignore saved positions that are no longer on any screen (monitor unplugged, DPI change).
        if any(screen.availableGeometry().intersects(rect) for screen in QGuiApplication.screens()):
            self.setGeometry(rect)
        if geo.maximized:
            self.setWindowState(self.windowState() | Qt.WindowState.WindowMaximized)

    def _on_preferences_changed(self, prefs: object) -> None:
        if not isinstance(prefs, Preferences):
            return
        history_toggled = prefs.remember_history != self._prefs.remember_history
        theme_changed = prefs.colour_theme != self._prefs.colour_theme
        if not prefs.ai_enabled and self.subtitle_job.running:
            self.subtitle_job.cancel()  # switching AI off stops work in progress
        self._prefs = replace(
            prefs,
            volume=self._prefs.volume,
            muted=self._prefs.muted,
            repeat_mode=self._prefs.repeat_mode,
            window=self._prefs.window,
            library_sort=self._prefs.library_sort,
            picture=self._prefs.picture,
            equalizer=self._prefs.equalizer,
            profiles=self._prefs.profiles,
        )
        self.player.set_preferences(self._prefs)
        self._store.save(self._prefs)
        self.status_bar_action.setChecked(self._prefs.show_status_bar)
        if not self.isFullScreen():
            self.statusBar().setVisible(self._prefs.show_status_bar)
        if theme_changed:
            self._apply_colour_theme(self._prefs.colour_theme)
            self.player.refresh_theme()
            self.home.refresh_theme()
            for button, glyph in self._nav_icons:
                nav_icon = glyph_icon(glyph, theme.TEXT, theme.TEXT_DISABLED, size=48)
                if nav_icon is not None:
                    button.setIcon(nav_icon)
            self._home_dirty = True  # Its cards hold pictures drawn in the old colours.
        if history_toggled:
            self._home_dirty = True
        self._refresh_ai_status()
        self._update_actions()

    def shuffle_list(self, paths: list[str]) -> None:
        self.show_page(self.player)
        self.player.play_queue(paths, random.randrange(len(paths)), shuffle=True)

    def build_theme_menu(self) -> QMenu:
        """Every theme, one click away. Choosing one goes through Settings, so both always agree."""
        menu = QMenu(self)
        for key, palette in THEMES.items():
            action = menu.addAction(theme_swatch(palette.accent, palette.accent2), palette.label)
            action.setCheckable(True)
            action.setChecked(key == self._prefs.colour_theme)
            action.triggered.connect(lambda _=False, chosen=key: self.choose_colour_theme(chosen))
        return menu

    def build_animation_menu(self) -> QMenu:
        menu = QMenu(self)
        for style, label in STYLE_LABELS.items():
            action = menu.addAction(label)
            action.setCheckable(True)
            action.setChecked(self._prefs.visual_style == style.value)
            action.triggered.connect(lambda _=False, s=style: self._choose_animation(s))
        return menu

    def _show_animation_menu(self) -> None:
        self.build_animation_menu().exec(self.nav_animation.mapToGlobal(self.nav_animation.rect().topRight()))

    def _show_theme_menu(self) -> None:
        self.build_theme_menu().exec(self.nav_theme.mapToGlobal(self.nav_theme.rect().topRight()))

    def choose_colour_theme(self, key: str) -> None:
        combo = self.settings.colour_theme
        combo.setCurrentIndex(max(0, combo.findData(key)))

    def _on_repeat_changed(self, mode: object) -> None:
        self._prefs = replace(self._prefs, repeat_mode=str(mode))
        self.settings.set_preferences(self._prefs)
        self._store.save(self._prefs)

    def show_queue(self) -> None:
        queue, index = self.player.queue
        if len(queue) < 2:
            self.statusBar().showMessage("No playlist is playing")
            return
        names = [Path(path).stem if "://" not in path else path for path in queue]
        QueueDialog(names, index, self.player.play_queue_item, self).open()

    def _fill_sleep_menu(self) -> None:
        self.sleep_menu.clear()
        remaining = self.player.sleep_remaining_ms
        off = self.sleep_menu.addAction("Off")
        off.setCheckable(True)
        off.setChecked(remaining is None)
        off.triggered.connect(lambda: self.player.set_sleep_timer(None))
        if remaining is not None:
            left = self.sleep_menu.addAction(f"Pausing in {format_time(remaining)}")
            left.setEnabled(False)
        self.sleep_menu.addSeparator()
        for minutes in SLEEP_MINUTES:
            action = self.sleep_menu.addAction(f"{minutes} minutes")
            action.triggered.connect(lambda _=False, m=minutes: self.player.set_sleep_timer(m))

    def _fill_animation_menu(self) -> None:
        self.animation_menu.clear()
        for style, label in STYLE_LABELS.items():
            action = self.animation_menu.addAction(label)
            action.setCheckable(True)
            action.setChecked(self._prefs.visual_style == style.value)
            action.triggered.connect(lambda _=False, s=style: self._choose_animation(s))

    def _choose_status_bar(self, shown: bool) -> None:
        if shown == self._prefs.show_status_bar:
            return
        self._prefs = replace(self._prefs, show_status_bar=shown)
        self.settings.set_preferences(self._prefs)
        self._store.save(self._prefs)
        if not self.isFullScreen():
            self.statusBar().setVisible(shown)

    def _choose_animation(self, style: VisualStyle) -> None:
        self._prefs = replace(self._prefs, visual_style=style.value)
        self.player.set_preferences(self._prefs)
        self.settings.set_preferences(self._prefs)
        self._store.save(self._prefs)

    @staticmethod
    def _apply_colour_theme(key: str) -> None:
        if key == theme.current_theme:
            return
        theme.apply_theme(key)
        app = QGuiApplication.instance()
        if isinstance(app, QApplication):
            # Windows draws the title bar and some small parts of controls, and follows this for them.
            scheme = Qt.ColorScheme.Light if theme.is_light() else Qt.ColorScheme.Unknown
            app.styleHints().setColorScheme(scheme)
            app.setStyleSheet(theme.STYLESHEET)

    def _final_preferences(self) -> Preferences:
        normal = self.normalGeometry() if (self.isMaximized() or self.isFullScreen()) else self.geometry()
        maximized = self.isMaximized() or (self.isFullScreen() and self._was_maximized)
        prefs = replace(
            self._prefs,
            window=WindowGeometry(normal.x(), normal.y(), normal.width(), normal.height(), maximized),
        )
        if prefs.remember_volume:
            volume, muted = self.player.volume_state()
            prefs = replace(prefs, volume=volume, muted=muted)
        return prefs.normalized()

    # ------------------------------------------------------------ window
    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        urls = event.mimeData().urls()
        dropped_stream = bool(urls) and is_network_uri(urls[0].toString())  # a link from a browser (M8)
        if self.player.engine_is_ready and urls and (urls[0].isLocalFile() or dropped_stream):
            event.acceptProposedAction()
            self.home.set_drag_active(True)

    def dragLeaveEvent(self, event: QDragLeaveEvent) -> None:
        self.home.set_drag_active(False)
        super().dragLeaveEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:
        self.home.set_drag_active(False)
        urls = event.mimeData().urls()
        if urls and not urls[0].isLocalFile() and is_network_uri(urls[0].toString()):
            self.open_path(urls[0].toString())  # validated by the engine like a typed address
            event.acceptProposedAction()
            return
        if urls and urls[0].isLocalFile() and Path(urls[0].toLocalFile()).is_dir():
            self.add_library_folder(urls[0].toLocalFile())  # a dropped folder joins the library
            event.acceptProposedAction()
            return
        if urls and urls[0].isLocalFile():
            path = urls[0].toLocalFile()
            # A subtitle dropped onto a playing video is added to it; anything else is opened.
            if Path(path).suffix.lower() in SUBTITLE_EXTENSIONS and self.player.can_load_subtitles:
                self.show_page(self.player)
                self.player.load_subtitle_file(path)
            else:
                self.open_path(path)
            event.acceptProposedAction()

    def show_playback_info(self) -> PlaybackInfoDialog:
        if self._info_dialog is None:
            self._info_dialog = PlaybackInfoDialog(
                self.player.controller, lambda: self.player.last_error, self
            )
        self._info_dialog.show()
        self._info_dialog.raise_()
        return self._info_dialog

    def _show_shortcuts(self) -> None:
        rows = "".join(
            f"<tr><td><b>{keys}</b>&nbsp;&nbsp;</td><td>{what}</td></tr>" for keys, what in SHORTCUTS
        )
        extra = (
            "<tr><td><b>S</b></td><td>Stop</td></tr>"
            "<tr><td><b>F11 / double-click</b>&nbsp;&nbsp;</td><td>Fullscreen</td></tr>"
            "<tr><td><b>Esc</b></td><td>Leave fullscreen</td></tr>"
            "<tr><td><b>Ctrl+1 / 2 / 3</b>&nbsp;&nbsp;</td><td>Home / Now Playing / Settings</td></tr>"
            "<tr><td><b>Ctrl+I</b></td><td>Playback info</td></tr>"
            "<tr><td><b>Ctrl+L</b></td><td>Library</td></tr>"
            "<tr><td><b>Z</b></td><td>Shuffle</td></tr>"
            "<tr><td><b>R</b></td><td>Repeat: off, this file, all</td></tr>"
            "<tr><td><b>Q</b></td><td>Queue</td></tr>"
            "<tr><td><b>U</b></td><td>Add to or remove from favourites</td></tr>"
            "<tr><td><b>N / P</b></td><td>Next / previous in playlist</td></tr>"
            "<tr><td><b>Home</b></td><td>Start over</td></tr>"
            "<tr><td><b>Ctrl+E</b></td><td>Picture &amp; Sound</td></tr>"
            "<tr><td><b>Shift+S</b></td><td>Snapshot (Pictures\\Babarify Media Player)</td></tr>"
            "<tr><td><b>. / ,</b></td><td>Next / previous frame</td></tr>"
            "<tr><td><b>L</b></td><td>A-B repeat (set A, set B, off)</td></tr>"
            "<tr><td><b>V / B</b></td><td>Next subtitle / audio track</td></tr>"
            "<tr><td><b>G / H</b></td><td>Subtitles 50 ms earlier / later</td></tr>"
            "<tr><td><b>J / K</b></td><td>Audio 50 ms earlier / later</td></tr>"
            "<tr><td><b>Ctrl+D</b></td><td>Sync and delay</td></tr>"
            "<tr><td><b>Ctrl+Shift+O</b>&nbsp;&nbsp;</td><td>Load subtitle file</td></tr>"
            "<tr><td><b>Ctrl+N</b></td><td>Open network stream</td></tr>"
            "<tr><td><b>Ctrl+→ / Ctrl+←</b>&nbsp;&nbsp;</td><td>Next / previous chapter</td></tr>"
            "<tr><td><b>Ctrl+B</b></td><td>Add bookmark</td></tr>"
            "<tr><td><b>Ctrl+Shift+B</b>&nbsp;&nbsp;</td><td>Bookmarks</td></tr>"
            "<tr><td><b>Ctrl+Shift+I</b>&nbsp;&nbsp;</td><td>Media information</td></tr>"
            "<tr><td><b>Ctrl+Shift+G</b>&nbsp;&nbsp;</td><td>Generate subtitles (local AI)</td></tr>"
            "<tr><td><b>Ctrl+Shift+F</b>&nbsp;&nbsp;</td><td>Search spoken words</td></tr>"
            "<tr><td><b>F1</b></td><td>This list</td></tr>"
        )
        QMessageBox.information(
            self,
            "Keyboard shortcuts",
            f"<table>{rows}{extra}</table><br>Playback keys work on the Now Playing page.",
        )

    def _show_about(self) -> None:
        engine = ""
        if self.player.engine_is_ready:
            caps = self.player.controller.capabilities()
            engine = f"<br>Playback engine: {caps.engine_name} {caps.engine_version}"
        QMessageBox.about(
            self,
            f"About {PRODUCT_NAME}",
            f"<b>{PRODUCT_NAME}</b> {__version__}<br>{TAGLINE}<br><br>"
            f"Free, no ads, no account, no telemetry.{engine}",
        )

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._info_dialog is not None:
            self._info_dialog.close()
        if self._enhancements is not None:
            self._enhancements.close()
        self._store.save(self._final_preferences())
        # Rule: the engine must be closed while its host window still exists.
        self.player.shutdown()  # also saves the playback position
        self.library_service.shutdown()
        self.library_service.db.close()
        super().closeEvent(event)
