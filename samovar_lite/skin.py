"""Skin: colours, metrics, fonts and hand-drawn vector glyphs (no bitmap assets)."""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPalette, QPen, QPolygonF

# -- colours -------------------------------------------------------------------------------------
BG = QColor("#1e1e1e")
BG_HOVER = QColor("#2c2c2c")
BG_PRESS = QColor("#141414")
VIDEO_BG = QColor("#101010")
LINE = QColor("#000000")
ACCENT = QColor("#fae100")
KNOB = QColor("#f0f0f0")
ICON = QColor("#f0f0f0")
ICON_HOVER = QColor("#ffffff")
ICON_DIM = QColor("#777777")
ICON_OFF = QColor("#4a4a4a")
TEXT = QColor("#c5c5c5")
TEXT_BRIGHT = QColor("#f0f0f0")
TEXT_DIM = QColor("#777777")
LOGO = QColor("#333333")
PANEL = QColor("#191919")
PANEL_ALT = QColor("#1e1e1e")
SELECT = QColor("#3a3a3a")
DANGER = QColor("#e04a3f")
BUFFER = QColor("#4a4a4a")

# -- metrics (logical px, measured from the reference skin) --------------------------------------
FRAME = 3
TITLE_H = 30
SEEK_H = 20
CTRL_H = 40
BTN_W = 40
VOLUME_W = 102
MENU_BTN_W = 88
TITLE_BTN_W = 24

FONT_FAMILIES = ["Segoe UI", "Noto Sans", "Ubuntu Sans", "Ubuntu", "DejaVu Sans"]


def font(px: int = 12, bold: bool = False) -> QFont:
    f = QFont()
    f.setFamilies(FONT_FAMILIES)
    f.setPixelSize(px)
    f.setBold(bold)
    return f


def mono_font(px: int = 12) -> QFont:
    f = QFont()
    f.setFamilies(["DejaVu Sans Mono", "Noto Sans Mono", "Ubuntu Mono", "monospace"])
    f.setPixelSize(px)
    return f


def dark_palette() -> QPalette:
    pal = QPalette()
    window = QColor("#2b2b2b")
    pal.setColor(QPalette.Window, window)
    pal.setColor(QPalette.WindowText, QColor("#e4e4e4"))
    pal.setColor(QPalette.Base, QColor("#1f1f1f"))
    pal.setColor(QPalette.AlternateBase, QColor("#262626"))
    pal.setColor(QPalette.Text, QColor("#e4e4e4"))
    pal.setColor(QPalette.Button, QColor("#353535"))
    pal.setColor(QPalette.ButtonText, QColor("#e4e4e4"))
    pal.setColor(QPalette.BrightText, QColor("#ffffff"))
    pal.setColor(QPalette.ToolTipBase, QColor("#2b2b2b"))
    pal.setColor(QPalette.ToolTipText, QColor("#e4e4e4"))
    pal.setColor(QPalette.Highlight, QColor("#4a4a4a"))
    pal.setColor(QPalette.HighlightedText, QColor("#ffffff"))
    pal.setColor(QPalette.Link, ACCENT)
    pal.setColor(QPalette.PlaceholderText, QColor("#7a7a7a"))
    pal.setColor(QPalette.Light, QColor("#484848"))
    pal.setColor(QPalette.Midlight, QColor("#3c3c3c"))
    pal.setColor(QPalette.Mid, QColor("#2a2a2a"))
    pal.setColor(QPalette.Dark, QColor("#141414"))
    pal.setColor(QPalette.Shadow, QColor("#000000"))
    for role in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText):
        pal.setColor(QPalette.Disabled, role, QColor("#6c6c6c"))
    return pal


APP_QSS = """
QToolTip { background: #2b2b2b; color: #e4e4e4; border: 1px solid #000000; padding: 3px 6px; }
QMenu { background: #2b2b2b; border: 1px solid #000000; padding: 3px 0px; }
QMenu::item { color: #e4e4e4; padding: 5px 30px 5px 28px; background: transparent; }
QMenu::item:selected { background: #454545; color: #ffffff; }
QMenu::item:disabled { color: #6c6c6c; }
QMenu::separator { height: 1px; background: #3d3d3d; margin: 4px 0px; }
QMenu::indicator { width: 12px; height: 12px; left: 8px; }
QDialog, QTabWidget::pane { background: #2b2b2b; }
QTabWidget::pane { border: 1px solid #111111; }
QTabBar::tab { background: #232323; color: #a8a8a8; padding: 6px 14px; border: 1px solid #111111;
               border-bottom: none; margin-right: 1px; }
QTabBar::tab:selected { background: #2b2b2b; color: #ffffff; }
QPushButton { background: #3a3a3a; color: #e4e4e4; border: 1px solid #111111; padding: 5px 14px;
              min-width: 56px; }
QPushButton:hover { background: #474747; }
QPushButton:pressed { background: #2a2a2a; }
QPushButton:default { border: 1px solid #8a7c00; }
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QPlainTextEdit, QTextEdit, QFontComboBox {
    background: #1f1f1f; color: #e4e4e4; border: 1px solid #111111; padding: 3px 5px;
    selection-background-color: #5a5a5a; }
QComboBox QAbstractItemView { background: #2b2b2b; color: #e4e4e4; selection-background-color: #454545; }
QSlider::groove:horizontal { height: 2px; background: #000000; }
QSlider::sub-page:horizontal { background: #fae100; }
QSlider::handle:horizontal { background: #f0f0f0; width: 10px; height: 10px; margin: -4px 0px;
                             border-radius: 5px; }
QSlider::groove:vertical { width: 2px; background: #000000; }
QSlider::add-page:vertical { background: #fae100; }
QSlider::handle:vertical { background: #f0f0f0; width: 10px; height: 10px; margin: 0px -4px;
                           border-radius: 5px; }
QCheckBox, QLabel, QGroupBox, QRadioButton { color: #e4e4e4; }
QGroupBox { border: 1px solid #1a1a1a; margin-top: 10px; padding-top: 8px; }
QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0px 4px; }
QScrollBar:vertical { background: #191919; width: 10px; margin: 0px; }
QScrollBar::handle:vertical { background: #4a4a4a; min-height: 24px; }
QScrollBar::handle:vertical:hover { background: #606060; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QScrollBar:horizontal { background: #191919; height: 10px; margin: 0px; }
QScrollBar::handle:horizontal { background: #4a4a4a; min-width: 24px; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0px; }
"""


# -- glyphs --------------------------------------------------------------------------------------
# Every glyph is drawn from primitives on the reference skin's pixel grid. (cx, cy) is the centre of
# the button; for the pixel-art glyphs the pixel at offset (0, 0) covers [cx, cx+1) x [cy, cy+1).
def _gear_path(cx: float, cy: float) -> QPainterPath:
    teeth, r_out, r_in = 8, 7.0, 5.0
    half = math.pi / teeth
    points = []
    for i in range(teeth):
        base = 2 * math.pi * i / teeth
        for radius, delta in ((r_in, -half * 0.62), (r_out, -half * 0.36), (r_out, half * 0.36), (r_in, half * 0.62)):
            angle = base + delta
            points.append(QPointF(cx + radius * math.cos(angle), cy + radius * math.sin(angle)))
    path = QPainterPath()
    path.addPolygon(QPolygonF(points))
    path.closeSubpath()
    hole = QPainterPath()
    hole.addEllipse(QPointF(cx, cy), 2.1, 2.1)
    return path.subtracted(hole)


def draw_icon(p: QPainter, name: str, cx: float, cy: float, color: QColor):
    p.save()
    p.setPen(Qt.NoPen)
    p.setBrush(color)
    p.setRenderHint(QPainter.Antialiasing, False)

    def rect(x, y, w, h):
        p.fillRect(QRectF(cx + x, cy + y, w, h), color)

    def faint(x, y, w, h, alpha):
        tint = QColor(color)
        tint.setAlphaF(alpha)
        p.fillRect(QRectF(cx + x, cy + y, w, h), tint)

    def poly(*pts):
        p.setRenderHint(QPainter.Antialiasing, True)
        p.drawPolygon(QPolygonF([QPointF(cx + x, cy + y) for x, y in pts]))
        p.setRenderHint(QPainter.Antialiasing, False)

    def corners(pixels):
        for sx in (1, -1):
            for sy in (1, -1):
                for x, y in pixels:
                    rect(x if sx > 0 else -x, y if sy > 0 else -y, 1, 1)

    if name == "play":
        poly((-3, -5), (-1.28, -5), (5.6, 0), (-1.28, 5), (-3, 5))
    elif name == "pause":
        rect(-4, -5, 3, 10)
        rect(1, -5, 3, 10)
    elif name == "stop":
        p.setRenderHint(QPainter.Antialiasing, True)
        p.drawRoundedRect(QRectF(cx - 4, cy - 4, 8, 8), 0.8, 0.8)
    elif name == "prev":
        rect(-4, -4, 2, 8)
        poly((4.25, -4), (3.05, -4), (-2.55, 0), (3.05, 4), (4.25, 4))
    elif name == "next":
        poly((-4.25, -4), (-3.05, -4), (2.55, 0), (-3.05, 4), (-4.25, 4))
        rect(2, -4, 2, 8)
    elif name == "eject":
        poly((0, -4.2), (4, -0.2), (4, 1.36), (-4, 1.36), (-4, -0.2))
        rect(-4, 3, 8, 1)
    elif name == "menu":
        for dy in (-4, 0, 4):
            rect(-6, dy, 12, 1)
    elif name == "gear":
        p.setRenderHint(QPainter.Antialiasing, True)
        p.drawPath(_gear_path(cx, cy))
    elif name in ("volume", "volume_low", "volume_mute"):
        rect(-5, -2, 3, 4)
        rect(-6, -1, 1, 2)
        faint(-6, -2, 1, 1, 0.3)
        faint(-6, 1, 1, 1, 0.3)
        rect(-2, -3, 1, 6)
        rect(-1, -4, 2, 8)
        faint(0, -5, 1, 1, 0.45)
        faint(0, 4, 1, 1, 0.45)
        if name == "volume_mute":
            for i in range(5):
                rect(2 + i, -2 + i, 1, 1)
                rect(6 - i, -2 + i, 1, 1)
        else:
            rect(2, -2, 1, 4)
            if name == "volume":
                rect(4, -3, 1, 6)
    elif name == "pin":
        rect(-3, -5, 7, 1)
        rect(-2, -4, 5, 4)
        rect(-3, 0, 7, 1)
        rect(-4, 1, 9, 1)
        rect(0, 2, 1, 3)
        rect(-3, 5, 7, 1)
    elif name == "minimize":
        rect(-4, 3, 9, 2)
    elif name == "maximize":
        rect(-4, -4, 9, 3)
        rect(-4, -1, 1, 5)
        rect(4, -1, 1, 5)
        rect(-4, 4, 9, 1)
    elif name == "restore":
        rect(-4, -1, 7, 2)
        rect(-4, 1, 1, 3)
        rect(2, 1, 1, 3)
        rect(-4, 4, 7, 1)
        rect(-2, -4, 7, 1)
        rect(-2, -3, 1, 1)
        rect(4, -3, 1, 5)
        rect(3, 1, 1, 1)
    elif name == "fullscreen":
        corners([(-4, -4), (-3, -4), (-2, -4), (-4, -3), (-3, -3), (-4, -2), (-2, -2), (-1, -1)])
    elif name == "fullscreen_exit":
        corners([(-1, -1), (-2, -1), (-3, -1), (-1, -2), (-2, -2), (-1, -3), (-3, -3), (-4, -4)])
    elif name == "close":
        for i in range(4):
            for y in (-4 + i, 3 - i):
                rect(-4 + i, y, 2, 1)
                rect(3 - i, y, 2, 1)
    elif name == "chevron":
        for i in range(4):
            rect(-3 + i, i, 1, 1)
            rect(3 - i, i, 1, 1)
    elif name == "repeat":
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setPen(QPen(color, 1.4))
        p.setBrush(Qt.NoBrush)
        p.drawArc(QRectF(cx - 5, cy - 4, 10, 8), 40 * 16, 280 * 16)
        p.setPen(Qt.NoPen)
        p.setBrush(color)
        poly((2, -6.5), (6.5, -4), (2, -1.5))
    elif name == "shuffle":
        p.setRenderHint(QPainter.Antialiasing, True)
        pen = QPen(color, 1.3)
        pen.setCapStyle(Qt.FlatCap)
        p.setPen(pen)
        for pts in (((-6, -3), (-2, -3), (2, 3), (6, 3)), ((-6, 3), (-2, 3), (2, -3), (6, -3))):
            p.drawPolyline(QPolygonF([QPointF(cx + x, cy + y) for x, y in pts]))
    p.restore()


_LOGO_PATHS: dict[str, QPainterPath] = {}


def draw_logo(p: QPainter, cx: float, cy: float, scale: float = 1.0, text: str = "Samovar Lite"):
    """Idle-screen watermark: a dark disc with a play triangle, and the application name beside it."""
    path = _LOGO_PATHS.get(text)
    if path is None:
        path = QPainterPath()
        path.addText(0, 0, font(46), text)
        _LOGO_PATHS[text] = path
    bounds = path.boundingRect()
    # The 46 px outline is drawn slightly condensed and lowered, which matches the skin's proportions.
    sx, sy = 0.893 * scale, 0.935 * scale
    radius, gap = 32 * scale, 15 * scale
    left = round(cx - (2 * radius + gap + bounds.width() * sx) / 2)
    dcx, dcy = left + radius, cy + scale
    p.save()
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setPen(Qt.NoPen)
    p.setBrush(LOGO)
    p.drawEllipse(QPointF(dcx, dcy), radius, radius)
    p.setBrush(VIDEO_BG)
    p.drawPolygon(
        QPolygonF(
            [
                QPointF(dcx - 9.2 * scale, dcy - 14.7 * scale),
                QPointF(dcx - 9.2 * scale, dcy + 14.7 * scale),
                QPointF(dcx + 15.3 * scale, dcy),
            ]
        )
    )
    p.translate(left + 2 * radius + gap - bounds.left() * sx, dcy + 14.7 * scale)
    p.scale(sx, sy)
    p.fillPath(path, LOGO)
    p.restore()


def app_icon_pixmap(size: int = 256):
    """Application icon, drawn at run time: a yellow samovar with a play symbol on a dark tile."""
    from PySide6.QtGui import QPixmap

    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    p.scale(size / 100.0, size / 100.0)
    p.setPen(Qt.NoPen)
    p.setBrush(BG)
    p.drawRoundedRect(QRectF(6, 6, 88, 88), 20, 20)

    p.setBrush(ACCENT)
    p.drawEllipse(QPointF(50, 19), 3.6, 3.6)  # finial
    p.drawPolygon(QPolygonF([QPointF(43, 25), QPointF(57, 25), QPointF(63, 32), QPointF(37, 32)]))  # lid
    body = QPainterPath()
    body.moveTo(34, 34)
    body.cubicTo(22, 43, 27, 61, 42, 69)
    body.lineTo(58, 69)
    body.cubicTo(73, 61, 78, 43, 66, 34)
    body.closeSubpath()
    play = QPainterPath()
    play.addPolygon(QPolygonF([QPointF(45, 42), QPointF(45, 60), QPointF(60, 51)]))
    play.closeSubpath()
    p.drawPath(body.subtracted(play))
    p.drawRect(QRectF(45, 69, 10, 4))  # neck
    p.drawPolygon(QPolygonF([QPointF(37, 73), QPointF(63, 73), QPointF(69, 81), QPointF(31, 81)]))  # base
    handles = QPen(ACCENT, 3.6)
    handles.setCapStyle(Qt.RoundCap)
    p.setPen(handles)
    p.setBrush(Qt.NoBrush)
    for sign in (-1, 1):
        handle = QPainterPath()
        handle.moveTo(50 + sign * 19, 40)
        handle.cubicTo(50 + sign * 33, 38, 50 + sign * 33, 55, 50 + sign * 21, 55)
        p.drawPath(handle)
    p.end()
    return pm
