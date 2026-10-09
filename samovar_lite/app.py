"""Main window, input handling and the application entry point."""

from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import tempfile
import time

from PySide6.QtCore import QEvent, QPoint, QStandardPaths, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QCursor, QDesktopServices, QGuiApplication, QIcon, QImage, QKeySequence, QPainter
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QFileDialog, QWidget

from . import __version__, skin
from .dialogs import EQ_FREQS, ControlPanel, GoToDialog, PreferencesDialog, TextDialog, UrlDialog
from .engine import Engine, VideoWidget
from .menus import LANGS, build_main_menu, build_track_menu, track_label
from .playlist import PlaylistPanel
from .settings import Settings
from .util import (
    MEDIA_FILTER,
    PLAYLIST_EXT,
    SUB_FILTER,
    expand_paths,
    ext,
    fmt_time,
    human_size,
    is_sub,
    is_url,
    read_playlist_file,
    similar_files,
    title_of,
)
from .widgets import ControlBar, Logo, Osd, SeekBar, SeekBubble, TitleBar, VolumeBar

IPC_NAME = "samovar-lite-%d" % os.getuid()
MOD_MASK = (Qt.ShiftModifier | Qt.ControlModifier | Qt.AltModifier | Qt.MetaModifier | Qt.KeypadModifier).value
KEYPAD = Qt.KeypadModifier.value
SHIFT = Qt.ShiftModifier.value

# Physical-key fallback so shortcuts keep working while a non-Latin layout (e.g. Persian) is active.
_SCAN = {}
for _start, _chars in ((2, "1234567890-="), (16, "QWERTYUIOP[]"), (30, "ASDFGHJKL;'"), (44, "ZXCVBNM,./")):
    for _i, _ch in enumerate(_chars):
        _SCAN[_start + _i + 8] = ord(_ch)
_SCAN[41 + 8] = ord("`")
_SCAN[43 + 8] = ord("\\")
_SHIFTED = {
    "<": ",",
    ">": ".",
    "?": "/",
    "{": "[",
    "}": "]",
    "|": "\\",
    ":": ";",
    '"': "'",
    "!": "1",
    "@": "2",
    "#": "3",
    "$": "4",
    "%": "5",
    "^": "6",
    "&": "7",
    "*": "8",
    "(": "9",
    ")": "0",
    "_": "-",
    "+": "=",
    "~": "`",
}

VIDEO_CODECS = {
    "h264": "AVC1",
    "hevc": "HEVC",
    "mpeg4": "MP4V",
    "mpeg2video": "MPEG2",
    "vp9": "VP9",
    "vp8": "VP8",
    "av1": "AV1",
    "wmv3": "WMV3",
    "vc1": "VC1",
    "msmpeg4v3": "DIV3",
}
AUDIO_CODECS = {"eac3": "E-AC3", "truehd": "TrueHD", "vorbis": "Vorbis", "opus": "Opus"}


def canonical_key(event) -> int:
    key = event.key()
    mods = event.modifiers().value
    if 0x20 <= key <= 0x7E:
        ch = chr(key)
        if mods & SHIFT and not mods & KEYPAD:
            ch = _SHIFTED.get(ch, ch)
        return ord(ch.upper())
    if key < 0x01000000:
        return _SCAN.get(event.nativeScanCode(), key)
    return key


class Inhibitor:
    """Keeps the screen awake while a video plays (org.freedesktop.ScreenSaver over D-Bus).

    The inhibition lives on a private bus connection; dropping the connection releases it.
    """

    def __init__(self):
        self.active = False
        self._serial = 0
        self._name = ""

    def set(self, on: bool):
        if on == self.active:
            return
        try:
            from PySide6.QtDBus import QDBusConnection, QDBusInterface
        except ImportError:
            return
        try:
            if on:
                self._serial += 1
                self._name = "samovar-lite-inhibit-%d" % self._serial
                bus = QDBusConnection.connectToBus(QDBusConnection.SessionBus, self._name)
                if not bus.isConnected():
                    return
                iface = QDBusInterface(
                    "org.freedesktop.ScreenSaver", "/org/freedesktop/ScreenSaver", "org.freedesktop.ScreenSaver", bus
                )
                iface.call("Inhibit", "Samovar Lite", "Playing video")
            else:
                QDBusConnection.disconnectFromBus(self._name)
            self.active = on
        except Exception:
            pass


class Grip(QWidget):
    """Invisible resize handle along one window edge or corner."""

    def __init__(self, parent, edges, cursor):
        super().__init__(parent)
        self.edges = edges
        self.setCursor(cursor)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            window = self.window()
            window._forget_wanted_size()
            handle = window.windowHandle()
            if handle is not None:
                handle.startSystemResize(self.edges)
        event.accept()


class Fill(QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        self.hide()

    def paintEvent(self, event):
        QPainter(self).fillRect(self.rect(), skin.LINE)


class VideoArea(QWidget):
    clicked = Signal()
    doubleClicked = Signal()
    middleClicked = Signal()
    extraButton = Signal(int)
    contextRequested = Signal(QPoint)
    wheel = Signal(int)
    dragStarted = Signal()
    moved = Signal()

    def __init__(self, engine: Engine, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.NoFocus)
        self.video = VideoWidget(engine, self)
        self.logo = Logo(self)
        self.osd = Osd(self)
        for child in (self.video, self.logo, self.osd):
            child.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self._press = None
        self._skip_release = False
        self._wheel_acc = 0

    def resizeEvent(self, event):
        for child in (self.video, self.logo, self.osd):
            child.setGeometry(self.rect())

    def mousePressEvent(self, event):
        button = event.button()
        if button == Qt.LeftButton:
            self._press = event.position()
            self._skip_release = False
        elif button == Qt.MiddleButton:
            self.middleClicked.emit()
        elif button == Qt.BackButton:
            self.extraButton.emit(-1)
        elif button == Qt.ForwardButton:
            self.extraButton.emit(1)
        event.accept()

    def mouseMoveEvent(self, event):
        self.moved.emit()
        if self._press is not None and event.buttons() & Qt.LeftButton:
            if (event.position() - self._press).manhattanLength() > 8:
                self._press = None
                self.dragStarted.emit()
        event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            if self._press is not None and not self._skip_release:
                self.clicked.emit()
            self._press = None
            self._skip_release = False
        elif event.button() == Qt.RightButton:
            self.contextRequested.emit(event.globalPosition().toPoint())
        event.accept()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._press = None
            self._skip_release = True
            self.doubleClicked.emit()
        event.accept()

    def wheelEvent(self, event):
        self._wheel_acc += event.angleDelta().y() or event.angleDelta().x()
        steps = int(self._wheel_acc / 120)
        if steps:
            self._wheel_acc -= steps * 120
            self.wheel.emit(steps)
        event.accept()


class Player(QWidget):
    screenshotDone = Signal(str, bool, str)

    def __init__(self, settings: Settings, silent: bool = False, verbose: bool = False):
        super().__init__()
        self.settings = settings
        self.setWindowFlags(
            Qt.Window | Qt.FramelessWindowHint | Qt.WindowMinimizeButtonHint | Qt.WindowMaximizeButtonHint
        )
        self.setWindowTitle("Samovar Lite")
        self.setMinimumSize(336, 250)
        self.setAcceptDrops(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMouseTracking(True)
        self.setAttribute(Qt.WA_OpaquePaintEvent, True)

        self.state: dict = {"idle-active": True}
        self.current_path: str | None = None
        self.playlist_visible = bool(settings["playlist_visible"])
        self.info_visible = False
        self.aspect_name = "Default"
        self.display_mode = "fit"
        self.flips = {"hflip": False, "vflip": False}
        self.normalize = False
        self._eq_active = False
        self._file_ready = False
        self._gl_ready = False
        self._pending_open: list = []
        self._pending_subs: list[str] = []
        self._autofit_pending = False
        self._resumed_at = None
        self._last_pos = 0.0
        self._seek_target = (0.0, 0.0)
        self._fail_count = 0
        self._was_maximized = False
        self._state_changed = 0.0
        self._wanted_size = None
        self._fs_top = self._fs_bottom = self._fs_right = self._fs_pin = False
        self._cursor_hidden = False
        self._closing = False
        self._mouse_in_video = False
        self._sub_margin = None
        self._menu = None
        self._panel = None
        self._wayland = QGuiApplication.platformName().startswith("wayland")
        self.inhibitor = Inhibitor()

        self.engine = Engine(settings, silent=silent, verbose=verbose, parent=self)
        self.engine.prop.connect(self._on_prop)
        self.engine.event.connect(self._on_event)

        # -- widgets (creation order is stacking order) -------------------------------------------
        self.video_area = VideoArea(self.engine, self)
        self.fs_top_bg, self.fs_bottom_bg, self.fs_right_bg = Fill(self), Fill(self), Fill(self)
        self.title = TitleBar(self)
        self.seek = SeekBar(self)
        self.volume = VolumeBar(self)
        self.ctrl = ControlBar(self)
        self.playlist = PlaylistPanel(self)
        self.bubble = SeekBubble(self)
        self.grips = [
            Grip(self, Qt.TopEdge, Qt.SizeVerCursor),
            Grip(self, Qt.BottomEdge, Qt.SizeVerCursor),
            Grip(self, Qt.LeftEdge, Qt.SizeHorCursor),
            Grip(self, Qt.RightEdge, Qt.SizeHorCursor),
            Grip(self, Qt.TopEdge | Qt.LeftEdge, Qt.SizeFDiagCursor),
            Grip(self, Qt.TopEdge | Qt.RightEdge, Qt.SizeBDiagCursor),
            Grip(self, Qt.BottomEdge | Qt.LeftEdge, Qt.SizeBDiagCursor),
            Grip(self, Qt.BottomEdge | Qt.RightEdge, Qt.SizeFDiagCursor),
        ]

        self.volume.set_volume(settings["volume"])
        self.volume.set_muted(settings["mute"])
        self.ctrl.time.remaining = bool(settings["show_remaining"])
        self.ctrl.time.set_times(0, 0)
        self.ctrl.list_btn.set_checked(self.playlist_visible)
        self.playlist.set_modes(settings["repeat"], settings["shuffle"])
        self.title.pin_btn.set_checked(settings["on_top"] != "never")

        self._connect()
        self._build_keymap()

        self._cursor_timer = QTimer(self)
        self._cursor_timer.setSingleShot(True)
        self._cursor_timer.setInterval(2000)
        self._cursor_timer.timeout.connect(self._hide_cursor)
        self._info_timer = QTimer(self)
        self._info_timer.setInterval(500)
        self._info_timer.timeout.connect(self._update_info)
        self._save_timer = QTimer(self)
        self._save_timer.setInterval(15000)
        self._save_timer.timeout.connect(self._autosave)
        self._save_timer.start()

        for child in self.findChildren(QWidget):
            child.installEventFilter(self)

        self.resize(int(settings["window_w"]), int(settings["window_h"]))
        self._layout()
        self.apply_eq()
        if settings["on_top"] == "always" and not self._wayland:
            self.setWindowFlag(Qt.WindowStaysOnTopHint, True)

    # ============================================================================================
    # wiring
    # ============================================================================================
    def _connect(self):
        va = self.video_area
        va.clicked.connect(self._video_clicked)
        va.doubleClicked.connect(self._video_double_clicked)
        va.middleClicked.connect(self.toggle_fullscreen)
        va.extraButton.connect(lambda d: self.next_file() if d > 0 else self.prev_file())
        va.contextRequested.connect(self.show_menu)
        va.wheel.connect(self.volume_step)
        va.dragStarted.connect(self._start_move)
        va.moved.connect(self._video_mouse_moved)
        va.video.ready.connect(self._on_gl_ready)

        t = self.title
        t.menuRequested.connect(lambda: self.show_menu(t.menu_btn.mapToGlobal(QPoint(0, skin.TITLE_H))))
        t.contextRequested.connect(lambda: self.show_menu(QCursor.pos()))
        t.pinClicked.connect(self.cycle_on_top)
        t.minimizeClicked.connect(self.showMinimized)
        t.maximizeClicked.connect(self.toggle_maximize)
        t.fullscreenClicked.connect(self.toggle_fullscreen)
        t.closeClicked.connect(self.close)
        t.dragStarted.connect(self._start_move)

        self.seek.seekRequested.connect(self._seek_bar_seek)
        self.seek.hoverChanged.connect(self._seek_hover)
        self.seek.wheel.connect(lambda d: self.seek_rel(d * self.settings["seek_small"]))
        self.volume.volumeRequested.connect(self.set_volume)
        self.volume.muteClicked.connect(self.toggle_mute)
        self.volume.wheel.connect(self.volume_step)

        c = self.ctrl
        c.play_btn.clicked.connect(self.toggle_pause)
        c.stop_btn.clicked.connect(self.stop)
        c.prev_btn.clicked.connect(self.prev_file)
        c.next_btn.clicked.connect(self.next_file)
        c.open_btn.clicked.connect(self.open_files_dialog)
        c.open_btn.rightClicked.connect(self.open_folder_dialog)
        c.gear_btn.clicked.connect(self.show_control_panel)
        c.list_btn.clicked.connect(self.toggle_playlist)
        c.time.clicked.connect(self._toggle_remaining)

        pl = self.playlist
        pl.playRequested.connect(self.play_row)
        pl.addFilesRequested.connect(lambda: self.open_files_dialog(append=True))
        pl.addFolderRequested.connect(lambda: self.open_folder_dialog(append=True))
        pl.addUrlRequested.connect(self.open_url_dialog)
        pl.closeRequested.connect(self.toggle_playlist)
        pl.repeatClicked.connect(self.cycle_repeat)
        pl.shuffleClicked.connect(self.toggle_shuffle)
        pl.changed.connect(self._update_title)
        pl.view.viewport().setMouseTracking(True)

        self.screenshotDone.connect(self._on_screenshot)
        self._prop_handlers = {
            "time-pos": self._p_time,
            "duration": self._p_duration,
            "pause": self._p_pause,
            "volume": self._p_volume,
            "mute": self._p_mute,
            "track-list": self._p_tracks,
            "chapter-list": self._p_chapters,
            "media-title": lambda v: self._update_title(),
            "idle-active": self._p_idle,
            "eof-reached": self._p_eof,
            "hwdec-current": lambda v: self._update_badges(),
            "video-params": self._p_video_params,
            "paused-for-cache": lambda v: self._update_buffering(),
            "cache-buffering-state": lambda v: self._update_buffering(),
            "demuxer-cache-time": self._p_cache,
            "ab-loop-a": lambda v: self._update_ab(),
            "ab-loop-b": lambda v: self._update_ab(),
        }

    def _build_keymap(self):
        self.keymap: dict = {}
        s = self.settings

        def bind(keys: str, fn, repeat: bool = False):
            for key in keys.split(" | "):
                combo = QKeySequence(key)[0]
                self.keymap[(combo.keyboardModifiers().value, combo.key().value)] = (fn, repeat)

        bind("Space | Media Play | Toggle Media Play/Pause | Media Pause", self.toggle_pause)
        bind("Return | Enter | Ctrl+Return | Alt+Return | F11", self.toggle_fullscreen)
        bind("Esc", self.exit_fullscreen)
        bind("Left", lambda: self.seek_rel(-s["seek_small"]), True)
        bind("Right", lambda: self.seek_rel(s["seek_small"]), True)
        bind("Ctrl+Left", lambda: self.seek_rel(-s["seek_medium"]), True)
        bind("Ctrl+Right", lambda: self.seek_rel(s["seek_medium"]), True)
        bind("Shift+Left", lambda: self.seek_rel(-s["seek_large"]), True)
        bind("Shift+Right", lambda: self.seek_rel(s["seek_large"]), True)
        bind("Ctrl+Alt+Left", lambda: self.seek_rel(-s["seek_huge"]), True)
        bind("Ctrl+Alt+Right", lambda: self.seek_rel(s["seek_huge"]), True)
        bind("Up", lambda: self.volume_step(1), True)
        bind("Down", lambda: self.volume_step(-1), True)
        bind("M", self.toggle_mute)
        bind("PgUp | Media Previous", self.prev_file)
        bind("PgDown | Media Next", self.next_file)
        bind("Shift+PgUp", lambda: self.chapter_step(-1))
        bind("Shift+PgDown", lambda: self.chapter_step(1))
        bind("Backspace | Home", lambda: self.seek_abs(0))
        bind("F", lambda: self.frame_step(1), True)
        bind("D", lambda: self.frame_step(-1), True)
        bind("C", lambda: self.change_speed(0.1), True)
        bind("X", lambda: self.change_speed(-0.1), True)
        bind("Z", lambda: self.set_speed(1.0))
        bind("G", self.go_to_dialog)
        bind("[", lambda: self.ab_set("a"))
        bind("]", lambda: self.ab_set("b"))
        bind("\\", self.ab_clear)
        bind(",", lambda: self.sub_delay(-0.5), True)
        bind(".", lambda: self.sub_delay(0.5), True)
        bind("/", lambda: self.sub_delay(None))
        bind("Shift+,", lambda: self.audio_delay(-0.05), True)
        bind("Shift+.", lambda: self.audio_delay(0.05), True)
        bind("Shift+/", lambda: self.audio_delay(None))
        bind("Alt+H", self.toggle_sub_visibility)
        bind("Alt+L", lambda: self.cycle_track("sub"))
        bind("L", lambda: self.show_track_menu("sub"))
        bind("A", lambda: self.show_track_menu("audio"))
        bind("Shift+A | Alt+A", lambda: self.cycle_track("audio"))
        bind("Alt+O", self.load_subtitle_dialog)
        bind("Alt+PgUp", lambda: self.sub_scale(0.1), True)
        bind("Alt+PgDown", lambda: self.sub_scale(-0.1), True)
        bind("Alt+Up", lambda: self.sub_move(-1), True)
        bind("Alt+Down", lambda: self.sub_move(1), True)
        bind("Ctrl+O | F3", self.open_files_dialog)
        bind("F2", self.open_folder_dialog)
        bind("Ctrl+U", self.open_url_dialog)
        bind("F4 | Media Stop", self.stop)
        bind("F5", self.show_preferences)
        bind("F6", self.toggle_playlist)
        bind("F7", self.show_control_panel)
        bind("F1", self.show_about)
        bind("Ctrl+F1", self.show_media_info)
        bind("Tab", self.toggle_info)
        bind("Ctrl+E", lambda: self.screenshot("video"))
        bind("Ctrl+Alt+E", lambda: self.screenshot("subtitles"))
        bind("Ctrl+C", lambda: self.screenshot("video", True))
        bind("Ctrl+Alt+C", lambda: self.screenshot("subtitles", True))
        bind("Ctrl+T", self.cycle_on_top)
        bind("1", lambda: self.set_window_scale(50))
        bind("2", lambda: self.set_window_scale(100))
        bind("3", lambda: self.set_window_scale(150))
        bind("4", lambda: self.set_window_scale(200))
        bind("Num+9", lambda: self.zoom(0.1), True)
        bind("Num+1", lambda: self.zoom(-0.1), True)
        bind("Num+4", lambda: self.pan(-0.02, 0), True)
        bind("Num+6", lambda: self.pan(0.02, 0), True)
        bind("Num+8", lambda: self.pan(0, -0.02), True)
        bind("Num+2", lambda: self.pan(0, 0.02), True)
        bind("Num+5", self.reset_geometry)
        bind("W", lambda: self.image_adjust("brightness", -1), True)
        bind("E", lambda: self.image_adjust("brightness", 1), True)
        bind("R", lambda: self.image_adjust("contrast", -1), True)
        bind("T", lambda: self.image_adjust("contrast", 1), True)
        bind("Y", lambda: self.image_adjust("saturation", -1), True)
        bind("U", lambda: self.image_adjust("saturation", 1), True)
        bind("I", lambda: self.image_adjust("hue", -1), True)
        bind("O", lambda: self.image_adjust("hue", 1), True)
        bind("Q", self.image_reset)
        bind("Alt+K", lambda: self.rotate(None))
        bind("Ctrl+Z", lambda: self.toggle_flip("hflip"))
        bind("Ctrl+V", lambda: self.toggle_flip("vflip"))
        bind("Ctrl+Q | Alt+F4", self.quit)
        bind("Menu | Shift+F10", lambda: self.show_menu(self.mapToGlobal(self.rect().center())))

    # ============================================================================================
    # layout and painting
    # ============================================================================================
    def paintEvent(self, event):
        QPainter(self).fillRect(self.rect(), skin.LINE)

    def resizeEvent(self, event):
        self._layout()
        if self._wanted_size is not None:
            QTimer.singleShot(200, self._confirm_size)

    def _chrome_extra(self):
        width = 2 * skin.FRAME + (int(self.settings["playlist_width"]) + 1 if self.playlist_visible else 0)
        height = 2 * skin.FRAME + skin.TITLE_H + 1 + 1 + skin.SEEK_H + 1 + skin.CTRL_H
        return width, height

    def _layout(self):
        W, H = self.width(), self.height()
        T, S, C, F, V = skin.TITLE_H, skin.SEEK_H, skin.CTRL_H, skin.FRAME, skin.VOLUME_W
        pw = int(self.settings["playlist_width"])
        fullscreen = self.isFullScreen()
        if fullscreen:
            top, bottom = self._fs_top, self._fs_bottom
            right = self._fs_right or self._fs_pin
            self.video_area.setGeometry(0, 0, W, H)
            self.fs_top_bg.setGeometry(0, 0, W, T + 1)
            self.title.setGeometry(0, 0, W, T)
            by = H - C - 1 - S - 1
            self.fs_bottom_bg.setGeometry(0, by, W, H - by)
            self.seek.setGeometry(0, by + 1, W - V, S)
            self.volume.move(W - V, by + 1)
            self.ctrl.setGeometry(0, H - C, W, C)
            py = T + 1 if top else 0
            ph = H - py - ((H - by) if bottom else 0)
            self.fs_right_bg.setGeometry(W - pw - 1, py, pw + 1, ph)
            self.playlist.setGeometry(W - pw, py, pw, ph)
        else:
            top = bottom = True
            right = self.playlist_visible
            x1 = W - F - ((pw + 1) if right else 0)
            cw = max(1, x1 - F)
            self.title.setGeometry(F, F, cw, T)
            vy = F + T + 1
            sy = H - F - C - 1 - S
            self.video_area.setGeometry(F, vy, cw, max(1, sy - 1 - vy))
            self.seek.setGeometry(F, sy, max(1, cw - V), S)
            self.volume.move(F + cw - V, sy)
            self.ctrl.setGeometry(F, H - F - C, cw, C)
            self.playlist.setGeometry(x1 + 1, F, pw, H - 2 * F)
        self.fs_top_bg.setVisible(fullscreen and top)
        self.fs_bottom_bg.setVisible(fullscreen and bottom)
        self.fs_right_bg.setVisible(fullscreen and right)
        self.title.setVisible(top)
        for widget in (self.seek, self.volume, self.ctrl):
            widget.setVisible(bottom)
        self.playlist.setVisible(right)
        if not bottom:
            self.bubble.hide()
        margin = 22
        if fullscreen and bottom:
            margin += int(round((S + C + 2) * 720.0 / max(1, H)))
        if margin != self._sub_margin:
            self._sub_margin = margin
            self.engine.set("sub-margin-y", margin)

        resizable = not (fullscreen or self.isMaximized())
        g, c = 5, 12
        rects = [
            (c, 0, W - 2 * c, g),
            (c, H - g, W - 2 * c, g),
            (0, c, g, H - 2 * c),
            (W - g, c, g, H - 2 * c),
            (0, 0, c, c),
            (W - c, 0, c, c),
            (0, H - c, c, c),
            (W - c, H - c, c, c),
        ]
        for grip, rect in zip(self.grips, rects, strict=False):
            grip.setGeometry(*rect)
            grip.setVisible(resizable)
            grip.raise_()

    def changeEvent(self, event):
        if event.type() == QEvent.ActivationChange and self._wanted_size is not None:
            QTimer.singleShot(200, self._confirm_size)
        if event.type() == QEvent.WindowStateChange:
            self._state_changed = time.monotonic()
            self.title.max_btn.set_icon("restore" if self.isMaximized() else "maximize")
            self.title.fs_btn.set_icon("fullscreen_exit" if self.isFullScreen() else "fullscreen")
            if not self.isFullScreen():
                self._fs_top = self._fs_bottom = self._fs_right = False
            self._layout()
            self._show_cursor()
        super().changeEvent(event)

    # ============================================================================================
    # mpv property and event handlers
    # ============================================================================================
    def _on_prop(self, name, value):
        self.state[name] = value
        handler = self._prop_handlers.get(name)
        if handler is not None:
            handler(value)

    def _on_event(self, name, data):
        if name == "file-loaded":
            self._file_ready = True
            self._fail_count = 0
            self.aspect_name = "Default"
            path = self.current_path
            if path:
                self.settings.add_recent(path)
            for sub in self._pending_subs:
                self.engine.cmd("sub-add", sub, "select")
            self._pending_subs = []
            self._update_title()
            self._update_logo()
            if self._resumed_at:
                self.osd("Resumed at %s  (Backspace: play from the beginning)" % fmt_time(self._resumed_at), 3000)
            elif path:
                self.osd(title_of(path))
        elif name == "end-file" and data.get("reason") == "error":
            self._file_ready = False
            self._fail_count += 1
            self.osd("Cannot open: %s" % title_of(self.current_path or ""), 3500, error=True)
            if self._fail_count < 3 and self.playlist.count() > 1:
                row = self.playlist.step(1, "off", False)
                if row >= 0:
                    QTimer.singleShot(1200, lambda: self.play_row(row))

    def _p_time(self, value):
        if value is None or not self._file_ready:
            return
        self._last_pos = float(value)
        self.seek.set_position(value)
        if not self.seek.dragging:
            self.ctrl.time.set_times(value, self.state.get("duration") or 0)

    def _p_duration(self, value):
        self.seek.set_duration(value or 0)
        if value:
            self.ctrl.time.set_times(self._last_pos if self._file_ready else 0, value)
            if self.current_path:
                self.playlist.set_duration(self.current_path, value)

    def _p_pause(self, value):
        self._update_play_state()

    def _p_volume(self, value):
        if value is not None:
            self.volume.set_volume(value)
            self.settings["volume"] = int(round(value))

    def _p_mute(self, value):
        self.volume.set_muted(bool(value))
        self.settings["mute"] = bool(value)

    def _p_tracks(self, value):
        self._update_logo()
        self._update_badges()

    def _p_chapters(self, value):
        self.seek.set_chapters([c.get("time", 0) for c in (value or [])])

    def _p_idle(self, idle):
        if idle:
            self._file_ready = False
            self._last_pos = 0.0
            self.seek.reset()
            self.ctrl.time.set_times(0, 0)
            self.video_area.osd.set_center("")
        self._update_logo()
        self._update_badges()
        self._update_title()
        self._update_play_state()

    def _p_eof(self, value):
        if not value or not self._file_ready:
            return
        if self.current_path:
            self.settings.set_position(self.current_path, None)
        repeat = self.settings["repeat"]
        if repeat == "one":
            self.engine.cmd("seek", 0, "absolute")
            self.engine.set("pause", False)
            return
        row = self.playlist.step(1, repeat, self.settings["shuffle"])
        if row >= 0:
            self.play_row(row, remember=False)
        else:
            self.stop(remember=False)

    def _p_video_params(self, value):
        if value and value.get("dw") and self._autofit_pending:
            self._autofit()
        self._update_badges()

    def _autofit(self):
        if not self._autofit_pending:
            return
        # Leaving full screen or maximized is asynchronous on Wayland; a resize sent while the
        # compositor is still switching state gets lost, so wait for the transition to settle.
        remaining = 0.5 - (time.monotonic() - self._state_changed)
        if remaining > 0:
            QTimer.singleShot(int(remaining * 1000) + 20, self._autofit)
            return
        self._autofit_pending = False
        if self.settings["autofit"]:
            self._fit_window()

    def _p_cache(self, value):
        if self.current_path and is_url(self.current_path) and value:
            self.seek.set_cache_end(float(value))
        else:
            self.seek.set_cache_end(None)

    def _update_ab(self):
        a, b = self.state.get("ab-loop-a"), self.state.get("ab-loop-b")
        self.seek.set_ab(a if isinstance(a, (int, float)) else None, b if isinstance(b, (int, float)) else None)

    def _update_buffering(self):
        if self.state.get("paused-for-cache") and self.has_file():
            self.video_area.osd.set_center("Buffering %d%%" % int(self.state.get("cache-buffering-state") or 0))
        else:
            self.video_area.osd.set_center("")

    def _update_play_state(self):
        playing = self.is_playing()
        self.ctrl.play_btn.set_icon("pause" if playing else "play")
        self.inhibitor.set(playing and self._has_video())
        self._apply_on_top()
        if not playing:
            self._show_cursor()
        else:
            self._cursor_timer.start()

    def _has_video(self) -> bool:
        return any(t.get("type") == "video" and t.get("selected") for t in self.tracks())

    def _update_logo(self):
        idle = bool(self.state.get("idle-active", True))
        audio_only = self._file_ready and not self._has_video()
        logo = self.video_area.logo
        logo.set_audio_title(title_of(self.current_path or "") if audio_only and not idle else "")
        logo.setVisible(idle or audio_only)

    def _update_badges(self):
        if not self.has_file() or not self._file_ready:
            self.ctrl.badges.set_items([])
            return
        items = []
        video = next((t for t in self.tracks() if t.get("type") == "video" and t.get("selected")), None)
        audio = next((t for t in self.tracks() if t.get("type") == "audio" and t.get("selected")), None)
        if video and not video.get("albumart"):
            hw = (self.state.get("hwdec-current") or "no") != "no"
            items.append(("H/W" if hw else "S/W", hw))
            codec = str(video.get("codec") or "")
            items.append((VIDEO_CODECS.get(codec, codec.upper()), False))
        if audio:
            codec = str(audio.get("codec") or "")
            items.append((AUDIO_CODECS.get(codec, codec.upper()), False))
        self.ctrl.badges.set_items(items)

    def _update_title(self):
        if not self.has_file() or not self.current_path:
            self.title.set_title("")
            self.setWindowTitle("Samovar Lite")
            return
        path = self.current_path
        name = (self.state.get("media-title") or path) if is_url(path) else title_of(path)
        name = str(name)
        count = self.playlist.count()
        row = self.playlist.current_row()
        prefix = "[%d/%d] " % (row + 1, count) if count > 1 and row >= 0 else ""
        self.title.set_title(prefix + name)
        self.setWindowTitle(name + " - Samovar Lite")

    # ============================================================================================
    # helpers
    # ============================================================================================
    def osd(self, text: str, ms: int = 1800, error: bool = False):
        self.video_area.osd.show_message(text, ms, skin.DANGER if error else None)

    def tracks(self) -> list:
        return self.state.get("track-list") or []

    def has_file(self) -> bool:
        return not self.state.get("idle-active", True)

    def is_playing(self) -> bool:
        return self.has_file() and not self.state.get("pause") and not self.state.get("eof-reached")

    def _position(self) -> float:
        return self._last_pos if self._file_ready else 0.0

    def _duration(self) -> float:
        return float(self.state.get("duration") or 0)

    def _remember_position(self):
        path = self.current_path
        if not path or not self._file_ready:
            return
        pos, dur = self._last_pos, self._duration()
        if self.settings["resume"] and pos > 5 and (not dur or pos < dur - max(10.0, dur * 0.03)):
            self.settings.set_position(path, pos)
        else:
            self.settings.set_position(path, None)

    def _autosave(self):
        if self.is_playing():
            self._remember_position()
            self.settings.save()

    # ============================================================================================
    # opening media
    # ============================================================================================
    def _on_gl_ready(self):
        self._gl_ready = True
        pending, self._pending_open = self._pending_open, []
        for paths, append in pending:
            self.open_paths(paths, append)

    def open_paths(self, paths: list[str], append: bool = False):
        paths = [p for p in paths if p]
        if not paths:
            return
        if not self._gl_ready:
            self._pending_open.append((paths, append))
            return
        items: list[str] = []
        for path in expand_paths(paths):
            if not is_url(path) and ext(path) in PLAYLIST_EXT and ext(path) != ".cue":
                items.extend(read_playlist_file(path))
            else:
                items.append(path)
        subs = [p for p in items if is_sub(p)]
        media = [p for p in items if not is_sub(p)]
        if not media:
            if subs and self.has_file():
                self.add_subtitles(subs)
            elif subs:
                self.osd("Open a video first, then add the subtitle", 3000, error=True)
            else:
                self.osd("No playable files found", 3000, error=True)
            return
        local = [p for p in media if not is_url(p)]
        if local:
            self.settings["last_dir"] = os.path.dirname(local[0])
        if append:
            first = self.playlist.add(media)
            if not self.has_file():
                self._pending_subs = subs
                self.play_row(first)
            else:
                self.osd("Added %d file%s to the playlist" % (len(media), "" if len(media) == 1 else "s"))
            return
        if len(paths) == 1 and len(media) == 1 and os.path.isfile(media[0]):
            group = similar_files(media[0])
            row = group.index(media[0])
        else:
            group, row = media, 0
        self.playlist.set_items(group)
        self._pending_subs = subs
        self.play_row(row)

    def play_row(self, row: int, remember: bool = True):
        path = self.playlist.path(row)
        if not path:
            return
        if remember:
            self._remember_position()
        self.playlist.set_current(row)
        self.current_path = path
        self._file_ready = False
        self._last_pos = 0.0
        self._autofit_pending = True
        self.seek.reset()
        self.ctrl.time.set_times(0, 0)
        start = self.settings.get_position(path) if self.settings["resume"] else None
        self._resumed_at = start
        self.engine.set("pause", False)
        self.engine.load(path, start)
        self._update_title()

    def add_subtitles(self, paths: list[str]):
        if not self.has_file():
            return
        for path in paths:
            self.engine.cmd("sub-add", path, "select")
        self.engine.set("sub-visibility", True)
        self.settings["last_sub_dir"] = os.path.dirname(paths[-1])
        self.osd("Subtitle: %s" % title_of(paths[-1]), 2500)

    def stop(self, remember: bool = True):
        if remember:
            self._remember_position()
        self._file_ready = False
        self.engine.cmd("stop")
        self.settings.save()

    def prev_file(self):
        self._step_file(-1)

    def next_file(self):
        self._step_file(1)

    def _step_file(self, direction: int):
        if self.playlist.count() == 0:
            return
        row = self.playlist.step(direction, self.settings["repeat"], self.settings["shuffle"])
        if row < 0:
            self.osd("Last file" if direction > 0 else "First file")
            return
        self.play_row(row)

    def clear_recent(self):
        self.settings["recent"] = []
        self.settings.save()

    # ============================================================================================
    # playback actions
    # ============================================================================================
    def toggle_pause(self):
        if not self.has_file():
            if self.playlist.count():
                self.play_row(max(0, self.playlist.current_row()))
            else:
                self.open_files_dialog()
            return
        if self.engine.get("eof-reached", False):
            self.engine.cmd("seek", 0, "absolute")
            self.engine.set("pause", False)
            return
        paused = not bool(self.engine.get("pause", False))
        self.engine.set("pause", paused)
        self.osd("Pause" if paused else "Play")

    def _seek_osd(self, target: float):
        dur = self._duration()
        self.osd("%s / %s" % (fmt_time(target), fmt_time(dur)) if dur else fmt_time(target))

    def seek_rel(self, amount: float):
        if not self.has_file() or not self._file_ready:
            return
        now = time.monotonic()
        base = self._seek_target[1] if now - self._seek_target[0] < 0.6 else self._last_pos
        dur = self._duration()
        target = max(0.0, base + amount)
        if dur:
            target = min(target, dur)
        self._seek_target = (now, target)
        self.engine.cmd("seek", amount, "relative")
        self._seek_osd(target)

    def seek_abs(self, seconds: float):
        if not self.has_file():
            return
        self.engine.cmd("seek", max(0.0, seconds), "absolute")
        self._seek_osd(seconds)

    def _seek_bar_seek(self, seconds: float, exact: bool):
        if not self.has_file():
            return
        self.engine.cmd("seek", "%.3f" % seconds, "absolute+exact" if exact else "absolute+keyframes")
        self.ctrl.time.set_times(seconds, self._duration())

    def _seek_hover(self, seconds: float, x: int):
        if seconds < 0 or not self.seek.isVisible():
            self.bubble.hide()
            return
        text = fmt_time(seconds)
        chapters = self.state.get("chapter-list") or []
        current = None
        for chapter in chapters:
            if chapter.get("time", 0) <= seconds:
                current = chapter
        if current and current.get("title"):
            text += "  " + str(current["title"])
        self.bubble.show_text(text, self.seek.x() + x, self.seek.y() - 1)

    def frame_step(self, direction: int):
        if not self.has_file():
            return
        self.engine.cmd("frame-step" if direction > 0 else "frame-back-step")
        self.osd("Next frame" if direction > 0 else "Previous frame", 900)

    def set_speed(self, value: float):
        value = max(0.2, min(12.0, round(value, 2)))
        self.engine.set("speed", value)
        self.osd("Speed: %.1fx" % value)

    def change_speed(self, delta: float):
        self.set_speed(float(self.engine.get("speed", 1.0) or 1.0) + delta)

    def go_to_dialog(self):
        if not self.has_file():
            return
        dialog = GoToDialog(self, self._position(), self._duration())
        if dialog.exec() and dialog.value is not None:
            self.seek_abs(dialog.value)

    def ab_set(self, which: str):
        if not self.has_file():
            return
        pos = self._position()
        self.engine.set("ab-loop-" + which, pos)
        self.osd("A-B repeat: %s point %s" % ("start" if which == "a" else "end", fmt_time(pos)))

    def ab_clear(self):
        self.engine.set("ab-loop-a", "no")
        self.engine.set("ab-loop-b", "no")
        self.osd("A-B repeat: off")

    def chapter_step(self, direction: int):
        if not (self.state.get("chapter-list") and self.has_file()):
            self.osd("No chapters")
            return
        self.engine.cmd("add", "chapter", direction)
        self.osd("Next chapter" if direction > 0 else "Previous chapter")

    def set_chapter(self, index: int):
        self.engine.set("chapter", index)

    def set_repeat(self, mode: str):
        self.settings["repeat"] = mode
        self.playlist.set_modes(mode, self.settings["shuffle"])
        self.osd({"off": "Repeat: off", "one": "Repeat: current file", "all": "Repeat: playlist"}[mode])

    def cycle_repeat(self):
        order = ["off", "one", "all"]
        self.set_repeat(order[(order.index(self.settings["repeat"]) + 1) % 3])

    def toggle_shuffle(self):
        self.settings["shuffle"] = not self.settings["shuffle"]
        self.playlist.set_modes(self.settings["repeat"], self.settings["shuffle"])
        self.osd("Shuffle: %s" % ("on" if self.settings["shuffle"] else "off"))

    def toggle_resume(self):
        self.settings["resume"] = not self.settings["resume"]
        self.osd("Remember playback position: %s" % ("on" if self.settings["resume"] else "off"))

    # -- subtitles -------------------------------------------------------------------------------
    def toggle_sub_visibility(self):
        visible = not bool(self.engine.get("sub-visibility", True))
        self.engine.set("sub-visibility", visible)
        self.settings["sub_visible"] = visible
        self.osd("Subtitles: %s" % ("show" if visible else "hide"))

    def set_track(self, kind: str, track_id):
        prop = {"sub": "sid", "audio": "aid", "video": "vid"}[kind]
        self.engine.set(prop, track_id)
        label = {"sub": "Subtitle", "audio": "Audio", "video": "Video"}[kind]
        if track_id == "no":
            self.osd("%s: off" % label)
            return
        if kind == "sub":
            self.engine.set("sub-visibility", True)
        track = next((t for t in self.tracks() if t.get("type") == kind and t.get("id") == track_id), None)
        self.osd("%s: %s" % (label, track_label(track).replace("&&", "&") if track else track_id), 2200)

    def cycle_track(self, kind: str):
        if not self.has_file():
            return
        ids = [t.get("id") for t in self.tracks() if t.get("type") == kind]
        if not ids:
            self.osd("No %s tracks" % ("subtitle" if kind == "sub" else kind))
            return
        choices = ids + (["no"] if kind == "sub" else [])
        current = next((t.get("id") for t in self.tracks() if t.get("type") == kind and t.get("selected")), "no")
        index = choices.index(current) if current in choices else -1
        self.set_track(kind, choices[(index + 1) % len(choices)])

    def set_secondary_sub(self, track_id):
        self.engine.set("secondary-sid", track_id)

    def sub_delay(self, delta):
        value = 0.0 if delta is None else round(float(self.engine.get("sub-delay", 0) or 0) + delta, 3)
        self.engine.set("sub-delay", value)
        self.osd("Subtitle sync: %+.1f sec" % value)

    def sub_scale(self, delta: float):
        value = self.engine.add("sub-scale", delta, 0.3, 3.0)
        self.osd("Subtitle size: %d%%" % round(value * 100))

    def sub_move(self, direction: int):
        value = self.engine.add("sub-pos", direction * 2, 0, 150)
        self.osd("Subtitle position: %d" % value)

    def sub_reset(self):
        self.engine.set("sub-scale", 1.0)
        self.engine.set("sub-pos", int(self.settings["sub_pos"]))
        self.engine.set("sub-delay", 0)
        self.osd("Subtitle size and position reset")

    def sub_seek(self, direction: int):
        if self.has_file():
            self.engine.cmd("sub-seek", direction)

    def set_sub_codepage(self, codepage: str):
        self.settings["sub_codepage"] = codepage
        self.engine.set("sub-codepage", codepage)
        if self.has_file():
            self.engine.cmd("sub-reload")
        self.osd("Subtitle encoding: %s" % codepage)

    # -- video -----------------------------------------------------------------------------------
    def set_aspect(self, label: str, value: str):
        self.aspect_name = label
        self.engine.set("video-aspect-override", value)
        self.osd("Aspect ratio: %s" % label)

    def set_display_mode(self, mode: str):
        self.display_mode = mode
        self.engine.set("keepaspect", mode != "stretch")
        self.engine.set("panscan", 1.0 if mode == "fill" else 0.0)
        self.engine.set("video-unscaled", mode == "original")
        self.osd(
            {
                "fit": "Keep aspect ratio",
                "fill": "Fill window (crop)",
                "stretch": "Stretch to window",
                "original": "Original size",
            }[mode]
        )

    def zoom(self, delta: float):
        value = self.engine.add("video-zoom", delta, -2.0, 3.0)
        self.osd("Zoom: %d%%" % round(2**value * 100))

    def pan(self, dx: float, dy: float):
        if dx:
            self.engine.add("video-pan-x", dx, -3.0, 3.0)
        if dy:
            self.engine.add("video-pan-y", dy, -3.0, 3.0)

    def reset_geometry(self):
        for prop in ("video-zoom", "video-pan-x", "video-pan-y"):
            self.engine.set(prop, 0)
        self.set_aspect("Default", "-1")
        self.set_display_mode("fit")
        self.osd("Pan & Scan reset")

    def rotate(self, degrees):
        if degrees is None:
            degrees = (int(self.engine.get("video-rotate", 0) or 0) + 90) % 360
        self.engine.set("video-rotate", degrees)
        self.osd("Rotation: %d°" % degrees)

    def toggle_flip(self, name: str):
        self.flips[name] = not self.flips[name]
        self.engine.cmd("vf", "toggle", "@fp%s:%s" % (name, name))
        self.osd(
            "%s: %s"
            % ("Flip horizontally" if name == "hflip" else "Flip vertically", "on" if self.flips[name] else "off")
        )

    def image_adjust(self, prop: str, direction: int):
        value = self.engine.add(prop, direction * 2, -100, 100)
        self.osd("%s: %+d" % (prop.capitalize(), value))

    def image_reset(self):
        for prop in ("brightness", "contrast", "saturation", "hue", "gamma"):
            self.engine.set(prop, 0)
        self.osd("Image adjustments reset")

    def toggle_deinterlace(self):
        value = not bool(self.engine.get("deinterlace", False))
        self.engine.set("deinterlace", value)
        self.osd("Deinterlace: %s" % ("on" if value else "off"))

    def set_hwdec(self, enabled: bool):
        self.settings["hwdec"] = bool(enabled)
        self.engine.set("hwdec", Engine.hwdec_value(enabled))
        self.osd("Hardware decoding: %s" % ("on" if enabled else "off"))

    # -- audio -----------------------------------------------------------------------------------
    def set_volume(self, value: int):
        value = max(0, min(100, int(value)))
        self.engine.set("volume", value)
        if value > 0 and self.state.get("mute"):
            self.engine.set("mute", False)
        self.volume.set_volume(value)
        self.osd("Volume: %d%%" % value)

    def volume_step(self, direction: int):
        self.set_volume(self.volume.volume + direction * int(self.settings["volume_step"]))

    def toggle_mute(self):
        muted = not bool(self.engine.get("mute", False))
        self.engine.set("mute", muted)
        self.osd("Mute: %s" % ("on" if muted else "off"))

    def audio_delay(self, delta):
        value = 0.0 if delta is None else round(float(self.engine.get("audio-delay", 0) or 0) + delta, 3)
        self.engine.set("audio-delay", value)
        self.osd("Audio sync: %+.2f sec" % value)

    def set_audio_device(self, name: str):
        self.engine.set("audio-device", name)

    def set_normalize(self, enabled: bool):
        enabled = bool(enabled)
        if enabled == self.normalize:
            return
        if enabled:
            self.engine.cmd("af", "add", "@fpnorm:lavfi=[dynaudnorm=g=5:f=250:r=0.9:p=1]")
        else:
            self.engine.cmd("af", "remove", "@fpnorm")
        self.normalize = bool(enabled)
        self.osd("Normalize volume: %s" % ("on" if enabled else "off"))

    def toggle_normalize(self):
        self.set_normalize(not self.normalize)

    def apply_eq(self):
        gains = list(self.settings["eq"])[:10]
        bands = [(f, g) for f, g in zip(EQ_FREQS, gains, strict=False) if g]
        if self.settings["eq_enabled"] and bands:
            chain = ",".join("equalizer=f=%d:t=o:w=1:g=%d" % band for band in bands)
            self.engine.cmd("af", "add", "@fpeq:lavfi=[%s]" % chain)
            self._eq_active = True
        elif self._eq_active:
            self.engine.cmd("af", "remove", "@fpeq")
            self._eq_active = False

    # -- capture ---------------------------------------------------------------------------------
    def _screenshot_dir(self) -> str:
        folder = self.settings["screenshot_dir"]
        if not folder:
            pictures = QStandardPaths.writableLocation(QStandardPaths.PicturesLocation) or os.path.expanduser("~")
            folder = os.path.join(pictures, "Samovar Lite")
        return os.path.expanduser(folder)

    def screenshot(self, mode: str = "video", clipboard: bool = False):
        if not self.has_file():
            return
        if clipboard:
            path = os.path.join(tempfile.gettempdir(), "samovar-lite-clip-%d.png" % os.getpid())
        else:
            folder = self._screenshot_dir()
            try:
                os.makedirs(folder, exist_ok=True)
            except OSError:
                self.osd("Cannot create folder: %s" % folder, 3500, error=True)
                return
            stem = os.path.splitext(title_of(self.current_path or "frame"))[0][:80].replace("/", "_")
            pos = self._position()
            base = "%s_%s.%03d" % (stem, fmt_time(pos).replace(":", "."), int(pos * 1000) % 1000)
            path = os.path.join(folder, base + ".png")
            counter = 1
            while os.path.exists(path):
                counter += 1
                path = os.path.join(folder, "%s_%d.png" % (base, counter))

        def done(error, _result):
            self.screenshotDone.emit(path, clipboard, str(error) if error else "")

        try:
            self.engine.mpv.command_async("screenshot-to-file", path, mode, callback=done)
        except Exception as exc:
            self.osd("Screenshot failed: %s" % exc, 3500, error=True)

    def _on_screenshot(self, path: str, clipboard: bool, error: str):
        if error or not os.path.exists(path):
            self.osd("Screenshot failed", 3500, error=True)
            return
        if clipboard:
            image = QImage(path)
            QGuiApplication.clipboard().setImage(image)
            try:
                os.remove(path)
            except OSError:
                pass
            self.osd("Frame copied to the clipboard")
        else:
            self.osd("Saved: %s" % os.path.basename(path), 2500)

    def open_screenshot_folder(self):
        folder = self._screenshot_dir()
        os.makedirs(folder, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(folder))

    # ============================================================================================
    # window actions
    # ============================================================================================
    def _start_move(self):
        if self.isFullScreen():
            return
        self._forget_wanted_size()
        handle = self.windowHandle()
        if handle is not None:
            handle.startSystemMove()

    def toggle_maximize(self):
        if self.isFullScreen():
            return
        self._state_changed = time.monotonic()
        self._forget_wanted_size()
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    def toggle_fullscreen(self):
        self._state_changed = time.monotonic()
        self._forget_wanted_size()
        if self.isFullScreen():
            if self._was_maximized:
                self.showMaximized()
            else:
                self.showNormal()
        else:
            self._was_maximized = self.isMaximized()
            self._fs_top = self._fs_bottom = self._fs_right = False
            self.showFullScreen()

    def exit_fullscreen(self):
        if self.isFullScreen():
            self.toggle_fullscreen()

    def _fit_window(self, scale: float | None = None) -> bool:
        params = self.state.get("video-params") or {}
        dw, dh = params.get("dw"), params.get("dh")
        if not dw or not dh or self.isFullScreen() or self.isMaximized():
            return False
        rotation = (int(params.get("rotate") or 0) + int(self.engine.get("video-rotate", 0) or 0)) % 180
        if rotation == 90:
            dw, dh = dh, dw
        ratio = self.devicePixelRatioF() or 1.0
        extra_w, extra_h = self._chrome_extra()
        screen = self.screen().availableGeometry()
        limited = False
        if scale is None:
            w, h = dw / ratio, dh / ratio
            pct = max(30, min(100, int(self.settings["autofit_max_pct"]))) / 100.0
            factor = min(1.0, (screen.width() * pct - extra_w) / w, (screen.height() * pct - extra_h) / h)
        else:
            w, h = dw * scale / ratio, dh * scale / ratio
            factor = min(1.0, (screen.width() - extra_w) / w, (screen.height() - extra_h) / h)
            limited = factor < 1.0
        w = max(self.minimumWidth() - 2 * skin.FRAME, round(w * factor))
        h = max(90, round(h * factor))
        self._request_size(int(w + extra_w), int(h + extra_h))
        return limited

    def _request_size(self, width: int, height: int):
        """Resize the window and keep that request alive for a few seconds.

        On Wayland the compositor can answer a later event (typically the window gaining focus)
        with the size it had before, when the resize happened while the window was hidden behind
        others. Until the request expires, or the user moves or resizes the window, the wanted
        size is applied again whenever the window ends up at a different one.
        """
        self._wanted_size = (width, height, time.monotonic() + 10.0)
        self.resize(width, height)
        QTimer.singleShot(350, self._confirm_size)

    def _forget_wanted_size(self):
        self._wanted_size = None

    def _confirm_size(self):
        wanted = self._wanted_size
        if wanted is None or self._closing:
            return
        width, height, expires = wanted
        if time.monotonic() > expires or self.isFullScreen() or self.isMaximized() or QGuiApplication.mouseButtons():
            return
        if (self.width(), self.height()) != (width, height):
            self.resize(width, height)

    def set_window_scale(self, percent: int):
        if not self.has_file() or not self._has_video():
            return
        if self.isFullScreen() or self.isMaximized():
            self.osd("Window size is not available in full screen")
            return
        limited = self._fit_window(percent / 100.0)
        self.osd("Window size: %d%%%s" % (percent, " (limited by screen)" if limited else ""))

    def toggle_autofit(self):
        self.settings["autofit"] = not self.settings["autofit"]

    def toggle_playlist(self):
        if self.isFullScreen():
            self._fs_pin = not self._fs_pin
            self._layout()
            return
        self.playlist_visible = not self.playlist_visible
        self.settings["playlist_visible"] = self.playlist_visible
        self.ctrl.list_btn.set_checked(self.playlist_visible)
        if not self.isMaximized():
            delta = int(self.settings["playlist_width"]) + 1
            self._request_size(self.width() + (delta if self.playlist_visible else -delta), self.height())
        self._layout()

    def set_on_top(self, mode: str):
        self.settings["on_top"] = mode
        self.title.pin_btn.set_checked(mode != "never")
        if self._wayland and mode != "never":
            self.osd("Always on top needs X11 mode: Preferences > General, or start with --x11", 4500)
            return
        self._apply_on_top()
        self.osd({"never": "On top: never", "always": "On top: always", "playing": "On top: while playing"}[mode])

    def cycle_on_top(self):
        order = ["never", "always", "playing"]
        self.set_on_top(order[(order.index(self.settings["on_top"]) + 1) % 3])

    def _apply_on_top(self):
        if self._wayland:
            return
        mode = self.settings["on_top"]
        want = mode == "always" or (mode == "playing" and self.is_playing())
        if want != bool(self.windowFlags() & Qt.WindowStaysOnTopHint) and not self.isFullScreen():
            self.setWindowFlag(Qt.WindowStaysOnTopHint, want)
            self.show()

    def _toggle_remaining(self):
        label = self.ctrl.time
        label.remaining = not label.remaining
        self.settings["show_remaining"] = label.remaining
        label.set_times(self._position(), self._duration())

    # -- info overlay ----------------------------------------------------------------------------
    def toggle_info(self):
        self.info_visible = not self.info_visible
        if self.info_visible:
            self._update_info()
            self._info_timer.start()
        else:
            self._info_timer.stop()
            self.video_area.osd.set_info("")

    def _update_info(self):
        self.video_area.osd.set_info(self.info_text(brief=True) if self.info_visible else "")

    def info_text(self, brief: bool = False) -> str:
        e = self.engine
        if not self.has_file():
            return "No file is open."
        path = self.current_path or ""
        lines = ["File      %s" % (title_of(path) if brief else path)]
        details = [d for d in (human_size(e.get("file-size")), str(e.get("file-format", "") or "")) if d]
        if details:
            lines.append("          " + ", ".join(details))
        params = self.state.get("video-params") or {}
        video = next((t for t in self.tracks() if t.get("type") == "video" and t.get("selected")), None)
        if video and params:
            fps = e.get("container-fps") or e.get("estimated-vf-fps") or 0
            hw = self.state.get("hwdec-current") or "no"
            lines.append(
                "Video     %s  %sx%s  %.3f fps  %s  %s"
                % (
                    str(video.get("codec") or "").upper(),
                    params.get("w", "?"),
                    params.get("h", "?"),
                    float(fps),
                    params.get("pixelformat", ""),
                    "hardware (%s)" % hw if hw != "no" else "software",
                )
            )
            bitrate = e.get("video-bitrate")
            if bitrate and not brief:
                lines.append("          %.0f kb/s" % (bitrate / 1000.0))
        audio = next((t for t in self.tracks() if t.get("type") == "audio" and t.get("selected")), None)
        if audio:
            ap = e.get("audio-params", {}) or {}
            lang = LANGS.get(str(audio.get("lang") or "").lower(), audio.get("lang") or "")
            lines.append(
                "Audio     %s  %s Hz  %s ch  %s"
                % (str(audio.get("codec") or "").upper(), ap.get("samplerate", "?"), ap.get("channel-count", "?"), lang)
            )
        sub = next((t for t in self.tracks() if t.get("type") == "sub" and t.get("selected")), None)
        if sub:
            lines.append(
                "Subtitle  %s  sync %+.1f sec"
                % (track_label(sub).replace("&&", "&"), float(e.get("sub-delay", 0) or 0))
            )
        lines.append(
            "Playback  %s / %s  %.2fx  A/V %+.3f  dropped %s"
            % (
                fmt_time(self._position()),
                fmt_time(self._duration()),
                float(e.get("speed", 1) or 1),
                float(e.get("avsync", 0) or 0),
                int(e.get("frame-drop-count", 0) or 0) + int(e.get("decoder-frame-drop-count", 0) or 0),
            )
        )
        if not brief:
            lines.append("")
            lines.append("Tracks")
            for track in self.tracks():
                lines.append(
                    "  %-6s %s%s"
                    % (
                        track.get("type", ""),
                        track_label(track).replace("&&", "&"),
                        "  *" if track.get("selected") else "",
                    )
                )
            chapters = self.state.get("chapter-list") or []
            if chapters:
                lines.append("")
                lines.append("Chapters")
                for i, chapter in enumerate(chapters, 1):
                    lines.append("  %2d. %s  %s" % (i, fmt_time(chapter.get("time", 0)), chapter.get("title") or ""))
            lines.append("")
            lines.append("System")
            lines.append("  mpv      %s" % e.get("mpv-version", "?"))
            lines.append("  ffmpeg   %s" % e.get("ffmpeg-version", "?"))
            lines.append("  display  %s, scale %.2f" % (QGuiApplication.platformName(), self.devicePixelRatioF()))
            if e.log_lines:
                lines.append("")
                lines.append("Recent engine messages")
                lines.extend("  " + line for line in list(e.log_lines)[-15:])
        return "\n".join(lines)

    # ============================================================================================
    # dialogs and menus
    # ============================================================================================
    def show_menu(self, global_pos=None):
        self._show_cursor()
        self._menu = build_main_menu(self)
        self._menu.popup(global_pos if isinstance(global_pos, QPoint) else QCursor.pos())

    def show_track_menu(self, kind: str):
        if not self.has_file():
            return
        self._menu = build_track_menu(self, kind)
        pos = QCursor.pos()
        if not self.rect().contains(self.mapFromGlobal(pos)):
            pos = self.mapToGlobal(self.rect().center())
        self._menu.popup(pos)

    def open_files_dialog(self, append: bool = False):
        start = self.settings["last_dir"] or QStandardPaths.writableLocation(QStandardPaths.MoviesLocation)
        files, _ = QFileDialog.getOpenFileNames(self, "Open File(s)", start, MEDIA_FILTER)
        if files:
            self.open_paths(files, append=append)

    def open_folder_dialog(self, append: bool = False):
        start = self.settings["last_dir"] or QStandardPaths.writableLocation(QStandardPaths.MoviesLocation)
        folder = QFileDialog.getExistingDirectory(self, "Open Folder", start)
        if folder:
            self.open_paths([folder], append=append)

    def open_url_dialog(self):
        dialog = UrlDialog(self)
        if dialog.exec() and dialog.url:
            self.open_paths([dialog.url], append=dialog.append)

    def load_subtitle_dialog(self):
        if not self.has_file():
            self.osd("Open a video first")
            return
        start = self.settings["last_sub_dir"] or self.settings["last_dir"] or ""
        if self.current_path and not is_url(self.current_path):
            start = os.path.dirname(self.current_path)
        files, _ = QFileDialog.getOpenFileNames(self, "Load Subtitle", start, SUB_FILTER)
        if files:
            self.add_subtitles(files)

    def load_audio_dialog(self):
        if not self.has_file():
            return
        start = os.path.dirname(self.current_path) if self.current_path and not is_url(self.current_path) else ""
        path, _ = QFileDialog.getOpenFileName(self, "Load External Audio", start, "All files (*)")
        if path:
            self.engine.cmd("audio-add", path, "select")
            self.osd("Audio: %s" % title_of(path), 2500)

    def show_control_panel(self, tab: str | None = None):
        if self._panel is None:
            self._panel = ControlPanel(self)
        if isinstance(tab, str):
            self._panel.select_tab(tab)
        self._panel.show()
        self._panel.raise_()
        self._panel.activateWindow()

    def show_preferences(self, tab: str | None = None):
        dialog = PreferencesDialog(self)
        if isinstance(tab, str):
            dialog.select_tab(tab)
        dialog.exec()

    def apply_settings(self, hwdec_changed: bool = False):
        s, e = self.settings, self.engine
        e.set("sub-font-size", int(s["sub_size"]))
        e.set("sub-bold", bool(s["sub_bold"]))
        e.set("sub-font", s["sub_font"] or "sans-serif")
        e.set("sub-auto", s["sub_auto"])
        e.set("slang", s["preferred_sub_lang"])
        e.set("alang", s["preferred_audio_lang"])
        if e.get("sub-codepage") != s["sub_codepage"]:
            e.set("sub-codepage", s["sub_codepage"])
            if self.has_file():
                e.cmd("sub-reload")
        if hwdec_changed:
            e.set("hwdec", Engine.hwdec_value(s["hwdec"]))

    def show_media_info(self):
        TextDialog(self, "Playback/System Info", self.info_text()).exec()

    def show_about(self):
        e = self.engine
        text = (
            "Samovar Lite %s\n\n"
            "A PotPlayer-style media player for Linux, built on libmpv and Qt.\n"
            "Free software under the GNU GPL, version 3 or later.\n"
            "Not affiliated with Kakao Corp. or PotPlayer.\n\n"
            "mpv:     %s\nffmpeg:  %s\nQt:      %s (%s)\n\n"
            "Right-click the video for the full menu.\n"
            "Settings: ~/.config/samovar-lite/settings.json"
        ) % (
            __version__,
            e.get("mpv-version", "?"),
            e.get("ffmpeg-version", "?"),
            __import__("PySide6").__version__,
            QGuiApplication.platformName(),
        )
        TextDialog(self, "About", text, mono=False, size=(460, 300)).exec()

    def quit(self):
        self.close()

    # ============================================================================================
    # input
    # ============================================================================================
    def focusNextPrevChild(self, forward: bool) -> bool:
        return False  # Tab is a player shortcut, not focus navigation

    def keyPressEvent(self, event):
        mods = event.modifiers().value & MOD_MASK
        key = canonical_key(event)
        entry = self.keymap.get((mods, key)) or self.keymap.get((mods & ~KEYPAD, key))
        if entry is None:
            event.ignore()
            return
        fn, repeat = entry
        if event.isAutoRepeat() and not repeat:
            event.accept()
            return
        event.accept()
        fn()

    def _video_clicked(self):
        if self.has_file():
            self.toggle_pause()

    def _video_double_clicked(self):
        if self.has_file():
            self.toggle_pause()  # undo the pause toggled by the first click
        self.toggle_fullscreen()

    def _video_mouse_moved(self):
        self._mouse_in_video = True
        self._show_cursor()
        if self.is_playing():
            self._cursor_timer.start()

    def _show_cursor(self):
        if self._cursor_hidden:
            self._cursor_hidden = False
            self.video_area.unsetCursor()

    def _hide_cursor(self):
        if (
            self.is_playing()
            and self._mouse_in_video
            and self._has_video()
            and QApplication.activePopupWidget() is None
            and QApplication.activeModalWidget() is None
            and not QGuiApplication.mouseButtons()
        ):
            self._cursor_hidden = True
            self.video_area.setCursor(Qt.BlankCursor)

    def eventFilter(self, obj, event):
        kind = event.type()
        if kind == QEvent.MouseMove and self.isFullScreen() and isinstance(obj, QWidget):
            self._fs_mouse(obj.mapTo(self, event.position().toPoint()))
        elif kind == QEvent.Leave and obj is self.video_area:
            self._mouse_in_video = False
        return False

    def _fs_mouse(self, pos: QPoint):
        if QApplication.activePopupWidget() is not None:
            return
        w, h = self.width(), self.height()
        bottom_h = skin.SEEK_H + skin.CTRL_H + 2
        pw = int(self.settings["playlist_width"])
        top = pos.y() <= (skin.TITLE_H if self._fs_top else 2)
        bottom = pos.y() >= h - (bottom_h if self._fs_bottom else 4)
        right = pos.x() >= w - (pw if self._fs_right else 2) and not top and not bottom
        if (top, bottom, right) != (self._fs_top, self._fs_bottom, self._fs_right):
            self._fs_top, self._fs_bottom, self._fs_right = top, bottom, right
            self._layout()

    # -- drag and drop ---------------------------------------------------------------------------
    @staticmethod
    def _dropped_paths(mime) -> list[str]:
        paths: list[str] = []
        if mime.hasUrls():
            for url in mime.urls():
                paths.append(url.toLocalFile() if url.isLocalFile() else url.toString())
        elif mime.hasText():
            for line in mime.text().splitlines():
                line = line.strip()
                if is_url(line) or os.path.exists(line):
                    paths.append(line)
        return [p for p in paths if p]

    def dragEnterEvent(self, event):
        paths = self._dropped_paths(event.mimeData())
        if not paths:
            event.ignore()
            return
        event.setDropAction(Qt.CopyAction)
        event.accept()
        if all(is_sub(p) for p in paths):
            text = "Drop to load subtitle"
        elif event.modifiers() & Qt.ControlModifier:
            text = "Drop to add to playlist"
        else:
            text = "Drop to play"
        self.video_area.osd.set_center(text)

    def dragMoveEvent(self, event):
        event.setDropAction(Qt.CopyAction)
        event.accept()

    def dragLeaveEvent(self, event):
        self.video_area.osd.set_center("")

    def dropEvent(self, event):
        self.video_area.osd.set_center("")
        paths = self._dropped_paths(event.mimeData())
        if not paths:
            event.ignore()
            return
        on_playlist = self.playlist.isVisible() and self.playlist.geometry().contains(event.position().toPoint())
        append = on_playlist or bool(event.modifiers() & Qt.ControlModifier)
        event.setDropAction(Qt.CopyAction)
        event.accept()
        QTimer.singleShot(0, lambda: self.open_paths(paths, append=append))

    # ============================================================================================
    # shutdown
    # ============================================================================================
    def closeEvent(self, event):
        if self._closing:
            event.accept()
            return
        self._closing = True
        self._remember_position()
        if not (self.isFullScreen() or self.isMaximized()):
            self.settings["window_w"], self.settings["window_h"] = self.width(), self.height()
        self.settings["first_run"] = False
        self.settings.save()
        for timer in (self._save_timer, self._info_timer, self._cursor_timer):
            timer.stop()
        self.inhibitor.set(False)
        if self._panel is not None:
            self._panel.close()
        self.playlist.shutdown()
        # Order matters: no more paints, free mpv's GL objects while the context is alive, then
        # stop the core. The window is only hidden afterwards.
        self.engine.prop.disconnect(self._on_prop)
        self.engine.event.disconnect(self._on_event)
        self.video_area.video.shutdown()
        self.engine.shutdown()
        event.accept()
        QTimer.singleShot(0, QApplication.instance().quit)


# ================================================================================================
# single instance
# ================================================================================================
def send_to_running(paths: list[str]) -> bool:
    socket = QLocalSocket()
    socket.connectToServer(IPC_NAME)
    if not socket.waitForConnected(300):
        return False
    socket.write(json.dumps({"paths": paths}).encode("utf-8"))
    socket.flush()
    socket.waitForBytesWritten(1000)
    socket.disconnectFromServer()
    return True


def start_server(player: Player) -> QLocalServer:
    QLocalServer.removeServer(IPC_NAME)
    server = QLocalServer(player)
    server.setSocketOptions(QLocalServer.UserAccessOption)

    def on_connection():
        socket = server.nextPendingConnection()
        if socket is None:
            return

        def read():
            try:
                message = json.loads(bytes(socket.readAll()).decode("utf-8"))
            except ValueError:
                return
            paths = [str(p) for p in message.get("paths", []) if isinstance(p, str)]
            if paths:
                player.open_paths(paths)
            player.showNormal() if player.isMinimized() else None
            player.raise_()
            player.activateWindow()

        socket.readyRead.connect(read)
        socket.disconnected.connect(socket.deleteLater)

    server.newConnection.connect(on_connection)
    server.listen(IPC_NAME)
    return server


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="samovar-lite", description="PotPlayer-style media player for Linux.")
    parser.add_argument("files", nargs="*", help="media files, folders, playlists, subtitles or URLs")
    parser.add_argument("--x11", action="store_true", help="run through X11/XWayland (enables always-on-top)")
    parser.add_argument("--wayland", action="store_true", help="force native Wayland")
    parser.add_argument("--new", action="store_true", help="start a new instance instead of reusing a running one")
    parser.add_argument("-f", "--fullscreen", action="store_true", help="start in full screen")
    parser.add_argument("--verbose", action="store_true", help="print engine warnings to the terminal")
    parser.add_argument("--version", action="version", version="Samovar Lite " + __version__)
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)

    settings = Settings()
    if args.x11 or (settings["use_x11"] and not args.wayland):
        os.environ["QT_QPA_PLATFORM"] = "xcb"
    elif args.wayland or (os.environ.get("WAYLAND_DISPLAY") and not os.environ.get("QT_QPA_PLATFORM")):
        os.environ["QT_QPA_PLATFORM"] = "wayland;xcb"

    paths = [p if is_url(p) else os.path.abspath(p) for p in args.files]
    app = QApplication(sys.argv[:1])
    app.setApplicationName("Samovar Lite")
    app.setApplicationDisplayName("Samovar Lite")
    app.setDesktopFileName("samovar-lite")
    if not args.new and send_to_running(paths):
        return 0
    app.setStyle("Fusion")
    app.setPalette(skin.dark_palette())
    app.setFont(skin.font(13))
    app.setStyleSheet(skin.APP_QSS)
    app.setWindowIcon(QIcon(skin.app_icon_pixmap()))

    try:
        player = Player(settings, verbose=args.verbose)
    except Exception as exc:  # most likely libmpv is missing
        from PySide6.QtWidgets import QMessageBox

        QMessageBox.critical(
            None,
            "Samovar Lite",
            "The playback engine could not start:\n\n%s\n\n"
            "Install libmpv (sudo apt install libmpv2) or run ./setup.sh." % exc,
        )
        return 1
    if not args.new:
        player._server = start_server(player)
    player.open_paths(paths)
    if args.fullscreen:
        player.showFullScreen()
    else:
        player.show()

    # Python runs signal handlers between bytecodes, possibly in the middle of a paint, so the
    # handler only schedules the close; the timer gives Python a chance to notice the signal.
    def on_signal(*_):
        QTimer.singleShot(0, player.close)

    signal.signal(signal.SIGINT, on_signal)
    signal.signal(signal.SIGTERM, on_signal)
    wake = QTimer()
    wake.timeout.connect(lambda: None)
    wake.start(250)
    return app.exec()
