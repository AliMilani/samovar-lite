"""Skinned chrome widgets: buttons, title bar, seek bar, volume bar, control row and OSD."""

from __future__ import annotations

import time

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFontMetrics, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

from . import skin
from .util import fmt_time


class IconButton(QWidget):
    clicked = Signal()
    rightClicked = Signal()

    def __init__(self, icon: str, w: int, h: int, tip: str = "", color=None, parent=None):
        super().__init__(parent)
        self.icon = icon
        self.color = color or skin.ICON
        self.hover_color = skin.ICON_HOVER
        self.checked = False
        self.flat = False  # flat buttons never change their background
        self._hover = False
        self._down = False
        self.setFixedSize(w, h)
        self.setFocusPolicy(Qt.NoFocus)
        self.setMouseTracking(True)
        if tip:
            self.setToolTip(tip)

    def set_icon(self, icon: str):
        if icon != self.icon:
            self.icon = icon
            self.update()

    def set_checked(self, checked: bool):
        if checked != self.checked:
            self.checked = checked
            self.update()

    def enterEvent(self, event):
        self._hover = True
        self.update()

    def leaveEvent(self, event):
        self._hover = False
        self._down = False
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._down = True
            self.update()
        elif event.button() == Qt.RightButton:
            self.rightClicked.emit()
        event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self._down:
            self._down = False
            self.update()
            if self.rect().contains(event.position().toPoint()):
                self.clicked.emit()
        event.accept()

    def mouseDoubleClickEvent(self, event):
        self.mousePressEvent(event)

    def paintEvent(self, event):
        p = QPainter(self)
        bg = skin.BG
        if not self.flat and self.isEnabled():
            if self._down:
                bg = skin.BG_PRESS
            elif self._hover:
                bg = skin.BG_HOVER
        p.fillRect(self.rect(), bg)
        if not self.isEnabled():
            color = skin.ICON_OFF
        elif self.checked:
            color = skin.ACCENT
        elif self._hover:
            color = self.hover_color
        else:
            color = self.color
        skin.draw_icon(p, self.icon, self.width() // 2, self.height() // 2, color)


class MenuButton(QWidget):
    """The application-name button at the left of the title bar; opens the main menu."""

    clicked = Signal()

    def __init__(self, text: str = "Samovar Lite", parent=None):
        super().__init__(parent)
        self.text = text
        self._hover = False
        self._font = skin.font(12)
        # Text starts 11 px in; the chevron sits 11 px after it and 14 px before the right edge.
        self._chevron_x = 11 + QFontMetrics(self._font).horizontalAdvance(text) + 11
        self.setFixedSize(max(skin.MENU_BTN_W, self._chevron_x + 14), skin.TITLE_H)
        self.setFocusPolicy(Qt.NoFocus)
        self.setMouseTracking(True)

    def enterEvent(self, event):
        self._hover = True
        self.update()

    def leaveEvent(self, event):
        self._hover = False
        self.update()

    def mousePressEvent(self, event):
        if event.button() in (Qt.LeftButton, Qt.RightButton):
            self.clicked.emit()
        event.accept()

    def mouseDoubleClickEvent(self, event):
        event.accept()

    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(self.rect(), skin.BG_HOVER if self._hover else skin.BG)
        p.setFont(self._font)
        p.setPen(skin.TEXT_BRIGHT if self._hover else skin.TEXT)
        p.drawText(QPointF(11, 19), self.text)
        skin.draw_icon(p, "chevron", self.width() - 14, 13, skin.TEXT_BRIGHT)


class TitleBar(QWidget):
    menuRequested = Signal()
    pinClicked = Signal()
    minimizeClicked = Signal()
    maximizeClicked = Signal()
    fullscreenClicked = Signal()
    closeClicked = Signal()
    dragStarted = Signal()
    contextRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(skin.TITLE_H)
        self.setMouseTracking(True)
        self.title = ""
        self._press = None
        self.menu_btn = MenuButton(parent=self)
        self.menu_btn.clicked.connect(self.menuRequested)
        self.pin_btn = self._title_button("pin", "Always on top (Ctrl+T)")
        self.min_btn = self._title_button("minimize", "Minimize")
        self.max_btn = self._title_button("maximize", "Maximize")
        self.fs_btn = self._title_button("fullscreen", "Full screen (Enter)")
        self.close_btn = self._title_button("close", "Close (Alt+F4)")
        self.close_btn.hover_color = QColor("#ff6a5e")
        self.pin_btn.clicked.connect(self.pinClicked)
        self.min_btn.clicked.connect(self.minimizeClicked)
        self.max_btn.clicked.connect(self.maximizeClicked)
        self.fs_btn.clicked.connect(self.fullscreenClicked)
        self.close_btn.clicked.connect(self.closeClicked)
        self.buttons = [self.pin_btn, self.min_btn, self.max_btn, self.fs_btn, self.close_btn]

    def _title_button(self, icon, tip):
        btn = IconButton(icon, skin.TITLE_BTN_W, skin.TITLE_H, tip, color=skin.ICON_DIM, parent=self)
        btn.flat = True
        return btn

    def set_title(self, title: str):
        self.title = title
        self.update()

    def resizeEvent(self, event):
        x = self.width() - 126
        for btn in self.buttons:
            btn.move(x, 0)
            x += skin.TITLE_BTN_W

    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(self.rect(), skin.BG)
        w = self.width()
        p.fillRect(self.menu_btn.width(), 0, 1, self.height(), skin.LINE)
        p.fillRect(w - 131, 0, 1, self.height(), skin.LINE)
        if self.title:
            p.setFont(skin.font(12))
            p.setPen(skin.TEXT)
            room = w - 131 - self.menu_btn.width() - 22
            text = QFontMetrics(p.font()).elidedText(self.title, Qt.ElideMiddle, max(0, room))
            p.drawText(QPointF(self.menu_btn.width() + 11, 19), text)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._press = event.position()
        elif event.button() == Qt.RightButton:
            self.contextRequested.emit()
        event.accept()

    def mouseMoveEvent(self, event):
        if self._press is not None and event.buttons() & Qt.LeftButton:
            if (event.position() - self._press).manhattanLength() > 4:
                self._press = None
                self.dragStarted.emit()
        event.accept()

    def mouseReleaseEvent(self, event):
        self._press = None
        event.accept()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._press = None
            self.maximizeClicked.emit()
        event.accept()


class SeekBar(QWidget):
    seekRequested = Signal(float, bool)  # seconds, exact
    hoverChanged = Signal(float, int)  # seconds (or -1 when leaving), x in widget coordinates
    wheel = Signal(int)

    MARGIN = 5

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(skin.SEEK_H)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.NoFocus)
        self.duration = 0.0
        self.position = 0.0
        self.cache_end = None
        self.chapters: list[float] = []
        self.ab = (None, None)
        self.dragging = False
        self._drag_time = 0.0
        self._last_emit = 0.0
        self._hover = False

    # -- state -----------------------------------------------------------------------------------
    def set_duration(self, duration):
        self.duration = float(duration or 0)
        self.update()

    def set_position(self, position):
        self.position = float(position or 0)
        if not self.dragging:
            self.update()

    def set_chapters(self, chapters):
        self.chapters = list(chapters)
        self.update()

    def set_ab(self, a, b):
        self.ab = (a, b)
        self.update()

    def set_cache_end(self, value):
        self.cache_end = value
        self.update()

    def reset(self):
        self.duration = self.position = 0.0
        self.cache_end = None
        self.chapters = []
        self.ab = (None, None)
        self.dragging = False
        self.update()

    # -- geometry --------------------------------------------------------------------------------
    def _span(self):
        return self.MARGIN, max(1, self.width() - 2 * self.MARGIN)

    def time_at(self, x: float) -> float:
        left, span = self._span()
        return max(0.0, min(1.0, (x - left) / span)) * self.duration

    def _x_of(self, seconds: float) -> float:
        left, span = self._span()
        if self.duration <= 0:
            return left
        return left + max(0.0, min(1.0, seconds / self.duration)) * span

    # -- events ----------------------------------------------------------------------------------
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self.duration > 0:
            self.dragging = True
            self._drag_time = self.time_at(event.position().x())
            self._last_emit = time.monotonic()
            self.seekRequested.emit(self._drag_time, True)
            self.update()
        event.accept()

    def mouseMoveEvent(self, event):
        x = event.position().x()
        if self.duration > 0:
            self.hoverChanged.emit(self.time_at(x), int(x))
        if self.dragging:
            self._drag_time = self.time_at(x)
            now = time.monotonic()
            if now - self._last_emit > 0.05:
                self._last_emit = now
                self.seekRequested.emit(self._drag_time, False)
            self.update()
        event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.dragging:
            self.dragging = False
            self.position = self._drag_time
            self.seekRequested.emit(self._drag_time, True)
            self.update()
        event.accept()

    def mouseDoubleClickEvent(self, event):
        self.mousePressEvent(event)

    def enterEvent(self, event):
        self._hover = True
        self.update()

    def leaveEvent(self, event):
        self._hover = False
        self.hoverChanged.emit(-1.0, 0)
        self.update()

    def wheelEvent(self, event):
        delta = event.angleDelta().y() or event.angleDelta().x()
        if delta:
            self.wheel.emit(1 if delta > 0 else -1)
        event.accept()

    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(self.rect(), skin.BG)
        left, span = self._span()
        y = self.height() // 2 - 1
        p.fillRect(QRectF(left, y, span, 2), skin.LINE)
        if self.duration <= 0:
            return
        current = self._drag_time if self.dragging else self.position
        x = self._x_of(current)
        if self.cache_end and self.cache_end > current:
            p.fillRect(QRectF(x, y, self._x_of(self.cache_end) - x, 2), skin.BUFFER)
        a, b = self.ab
        if a is not None and b is not None and b > a:
            xa, xb = self._x_of(a), self._x_of(b)
            p.fillRect(QRectF(xa, y - 2, xb - xa, 1), skin.ACCENT)
        p.fillRect(QRectF(left, y, x - left, 2), skin.ACCENT)
        for chapter in self.chapters:
            if 0 < chapter < self.duration:
                p.fillRect(QRectF(round(self._x_of(chapter)), y - 2, 1, 6), skin.TEXT_DIM)
        for point in (a, b):
            if point is not None:
                p.fillRect(QRectF(round(self._x_of(point)), y - 4, 1, 4), skin.ACCENT)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setPen(Qt.NoPen)
        p.setBrush(skin.KNOB)
        radius = 4.5 if (self._hover or self.dragging) else 4.0
        p.drawEllipse(QPointF(max(left, x), y + 1), radius, radius)


class VolumeBar(QWidget):
    volumeRequested = Signal(int)
    muteClicked = Signal()
    wheel = Signal(int)

    LINE_X0 = 22
    LINE_X1 = 91
    KNOB_X0 = 26
    KNOB_X1 = 86

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(skin.VOLUME_W, skin.SEEK_H)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.NoFocus)
        self.volume = 100
        self.muted = False
        self._dragging = False
        self._hover_icon = False

    def set_volume(self, volume):
        self.volume = max(0, min(100, int(round(volume or 0))))
        self.setToolTip("Volume: %d%%" % self.volume)
        self.update()

    def set_muted(self, muted):
        self.muted = bool(muted)
        self.update()

    def _volume_at(self, x: float) -> int:
        frac = (x - self.KNOB_X0) / (self.KNOB_X1 - self.KNOB_X0)
        return int(round(max(0.0, min(1.0, frac)) * 100))

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            if event.position().x() < self.LINE_X0 - 4:
                self.muteClicked.emit()
            else:
                self._dragging = True
                self.volumeRequested.emit(self._volume_at(event.position().x()))
        event.accept()

    def mouseMoveEvent(self, event):
        hover_icon = event.position().x() < self.LINE_X0 - 4
        if hover_icon != self._hover_icon:
            self._hover_icon = hover_icon
            self.update()
        if self._dragging:
            self.volumeRequested.emit(self._volume_at(event.position().x()))
        event.accept()

    def mouseReleaseEvent(self, event):
        self._dragging = False
        event.accept()

    def mouseDoubleClickEvent(self, event):
        self.mousePressEvent(event)

    def leaveEvent(self, event):
        self._hover_icon = False
        self.update()

    def wheelEvent(self, event):
        delta = event.angleDelta().y() or event.angleDelta().x()
        if delta:
            self.wheel.emit(1 if delta > 0 else -1)
        event.accept()

    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(self.rect(), skin.BG)
        y = self.height() // 2 - 1
        if self.muted or self.volume == 0:
            icon = "volume_mute"
        elif self.volume < 50:
            icon = "volume_low"
        else:
            icon = "volume"
        skin.draw_icon(p, icon, 11, 10, skin.ICON_HOVER if self._hover_icon else skin.ICON_DIM)
        knob_x = self.KNOB_X0 + (self.KNOB_X1 - self.KNOB_X0) * self.volume / 100.0
        p.fillRect(QRectF(self.LINE_X0, y, self.LINE_X1 - self.LINE_X0, 2), skin.LINE)
        fill = skin.TEXT_DIM if self.muted else skin.ACCENT
        p.fillRect(QRectF(self.LINE_X0, y, knob_x - self.LINE_X0, 2), fill)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setPen(Qt.NoPen)
        p.setBrush(skin.KNOB)
        p.drawEllipse(QPointF(knob_x, y + 1), 4.0, 4.0)


class TimeLabel(QWidget):
    clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.position = 0.0
        self.duration = 0.0
        self.remaining = False
        self._font = skin.font(11)
        self._font.setLetterSpacing(self._font.SpacingType.AbsoluteSpacing, 0.2)
        self._text = ("00:00:00", " / 00:00:00")
        self.setFixedHeight(skin.CTRL_H)
        self.setFocusPolicy(Qt.NoFocus)
        self.setToolTip("Click to switch between elapsed and remaining time")
        self._fit()

    def _fit(self):
        fm = QFontMetrics(self._font)
        self.setFixedWidth(fm.horizontalAdvance(self._text[0] + self._text[1]) + 3)

    def set_times(self, position, duration):
        self.position = float(position or 0)
        self.duration = float(duration or 0)
        if self.remaining and self.duration > 0:
            left = "-" + fmt_time(max(0.0, self.duration - self.position))
        else:
            left = fmt_time(self.position)
        text = (left, " / " + fmt_time(self.duration))
        if text != self._text:
            resize = len(text[0]) != len(self._text[0])
            self._text = text
            if resize:
                self._fit()
                parent = self.parentWidget()
                if parent is not None:
                    parent.relayout()
            self.update()

    def refresh(self):
        self.set_times(self.position, self.duration)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        event.accept()

    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(self.rect(), skin.BG)
        p.setFont(self._font)
        left, right = self._text
        p.setPen(skin.TEXT_BRIGHT)
        p.drawText(QPointF(0, 25), left)
        p.setPen(skin.TEXT_DIM)
        p.drawText(QPointF(p.fontMetrics().horizontalAdvance(left), 25), right)


class InfoBadges(QWidget):
    """Small dim labels next to the time: decoder (H/W or S/W), video codec, audio codec."""

    clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.items: list[tuple[str, bool]] = []
        self._font = skin.font(10)
        self.setFixedHeight(skin.CTRL_H)
        self.setFocusPolicy(Qt.NoFocus)

    def set_items(self, items):
        items = [(text, bool(on)) for text, on in items if text]
        if items != self.items:
            self.items = items
            self.update()

    def wanted_width(self) -> int:
        fm = QFontMetrics(self._font)
        return sum(fm.horizontalAdvance(text) + 12 for text, _ in self.items)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        event.accept()

    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(self.rect(), skin.BG)
        p.setFont(self._font)
        fm = p.fontMetrics()
        x = 0
        for text, on in self.items:
            w = fm.horizontalAdvance(text)
            if x + w > self.width():
                break
            p.setPen(skin.ACCENT if on else skin.TEXT_DIM)
            p.drawText(QRectF(x, 0, w + 2, self.height() + 1), Qt.AlignVCenter | Qt.AlignLeft, text)
            x += w + 12


class ControlBar(QWidget):
    """Bottom row: transport buttons, time, badges, control-panel and playlist buttons."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(skin.CTRL_H)
        self.setMouseTracking(True)
        self.play_btn = self._button("play", "Play/Pause (Space)")
        self.stop_btn = self._button("stop", "Stop (F4)")
        self.prev_btn = self._button("prev", "Previous (PgUp)")
        self.next_btn = self._button("next", "Next (PgDn)")
        self.open_btn = self._button("eject", "Open file (F3)")
        self.transport = [self.play_btn, self.stop_btn, self.prev_btn, self.next_btn, self.open_btn]
        self.time = TimeLabel(self)
        self.badges = InfoBadges(self)
        self.gear_btn = IconButton("gear", 28, skin.CTRL_H, "Control panel (F7)", color=skin.ICON_DIM, parent=self)
        self.gear_btn.flat = True
        self.list_btn = self._button("menu", "Playlist (F6)")
        for i, btn in enumerate(self.transport):
            btn.move(i * (skin.BTN_W + 1), 0)
        self.time.move(5 * (skin.BTN_W + 1) + 10, 0)

    def resizeEvent(self, event):
        self.relayout()

    def _button(self, icon: str, tip: str) -> IconButton:
        return IconButton(icon, skin.BTN_W, skin.CTRL_H, tip, parent=self)

    def relayout(self):
        w = self.width()
        self.list_btn.move(w - skin.BTN_W, 0)
        self.gear_btn.move(w - 77, 0)
        time_end = self.time.x() + self.time.width()
        self.time.setVisible(time_end <= w - skin.BTN_W - 4)
        self.gear_btn.setVisible(self.gear_btn.x() >= time_end)
        room = self.gear_btn.x() - time_end - 14
        self.badges.setGeometry(time_end + 10, 0, max(0, room), skin.CTRL_H)
        self.badges.setVisible(room > 24)

    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(self.rect(), skin.BG)
        for i in range(1, 6):
            p.fillRect(i * (skin.BTN_W + 1) - 1, 0, 1, self.height(), skin.LINE)
        p.fillRect(self.width() - skin.BTN_W - 1, 0, 1, self.height(), skin.LINE)


class SeekBubble(QWidget):
    """Time tooltip that follows the pointer over the seek bar."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self._font = skin.font(11)
        self.text = ""
        self.hide()

    def show_text(self, text: str, center_x: int, bottom_y: int):
        self.text = text
        fm = QFontMetrics(self._font)
        w = fm.horizontalAdvance(text) + 14
        h = fm.height() + 6
        parent = self.parentWidget()
        x = max(2, min(center_x - w // 2, (parent.width() if parent else 9999) - w - 2))
        self.setGeometry(x, bottom_y - h, w, h)
        self.show()
        self.raise_()
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#000000"))
        p.fillRect(self.rect().adjusted(1, 1, -1, -1), QColor("#2b2b2b"))
        p.setFont(self._font)
        p.setPen(skin.TEXT_BRIGHT)
        p.drawText(self.rect(), Qt.AlignCenter, self.text)


class Osd(QWidget):
    """Outlined on-screen text at the top-left of the video, plus the optional info block."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.message = ""
        self.color = QColor("#ffffff")
        self.info = ""
        self.center_text = ""
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._clear)

    def show_message(self, text: str, ms: int = 1800, color: QColor | None = None):
        self.message = text
        self.color = color or QColor("#ffffff")
        self._timer.start(ms)
        self.update()

    def set_info(self, text: str):
        if text != self.info:
            self.info = text
            self.update()

    def set_center(self, text: str):
        if text != self.center_text:
            self.center_text = text
            self.update()

    def _clear(self):
        self.message = ""
        self.update()

    def _outlined(self, p: QPainter, x: float, y: float, text: str, font, color, width: float):
        path = QPainterPath()
        fm = QFontMetrics(font)
        for i, line in enumerate(text.split("\n")):
            path.addText(QPointF(x, y + fm.ascent() + i * fm.lineSpacing()), font, line)
        pen = QPen(QColor(0, 0, 0, 225), width)
        pen.setJoinStyle(Qt.RoundJoin)
        p.strokePath(path, pen)
        p.fillPath(path, color)
        return fm.lineSpacing() * (text.count("\n") + 1)

    def paintEvent(self, event):
        if not (self.message or self.info or self.center_text):
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        size = int(max(15, min(30, self.height() / 22)))
        y = 8.0
        if self.message:
            y += self._outlined(p, 12, y, self.message, skin.font(size, True), self.color, 3.0) + 6
        if self.info:
            font = skin.mono_font(max(11, int(size * 0.62)))
            fm = QFontMetrics(font)
            lines = self.info.split("\n")
            w = max(fm.horizontalAdvance(line) for line in lines) + 20
            h = fm.lineSpacing() * len(lines) + 14
            p.fillRect(QRectF(10, y, w, h), QColor(16, 16, 16, 200))
            p.setFont(font)
            p.setPen(QColor("#e4e4e4"))
            for i, line in enumerate(lines):
                p.drawText(QPointF(20, y + 7 + fm.ascent() + i * fm.lineSpacing()), line)
        if self.center_text:
            font = skin.font(max(14, size - 4), True)
            fm = QFontMetrics(font)
            w = fm.horizontalAdvance(self.center_text)
            self._outlined(
                p,
                (self.width() - w) / 2,
                (self.height() - fm.height()) / 2,
                self.center_text,
                font,
                QColor("#ffffff"),
                3.0,
            )


class Logo(QWidget):
    """Idle screen: the mark on the dark video background."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.audio_title = ""

    def set_audio_title(self, title: str):
        if title != self.audio_title:
            self.audio_title = title
            self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(self.rect(), skin.VIDEO_BG)
        w, h = self.width(), self.height()
        scale = max(0.35, min(1.0, w / 400.0, h / 150.0))
        skin.draw_logo(p, w / 2, h / 2, scale)
        if self.audio_title:
            p.setFont(skin.font(13))
            p.setPen(skin.TEXT_DIM)
            p.drawText(
                QRectF(10, h / 2 + 44 * scale, w - 20, 24),
                Qt.AlignHCenter | Qt.AlignTop,
                QFontMetrics(p.font()).elidedText(self.audio_title, Qt.ElideMiddle, w - 20),
            )
