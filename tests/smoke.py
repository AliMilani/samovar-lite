#!/usr/bin/env python3
"""End-to-end smoke test: drives the real window with generated clips.

    .venv/bin/python tests/smoke.py

Needs ffmpeg and a display (a real session, or `xvfb-run -s "-screen 0 1920x1080x24"`). It uses a
throw-away settings folder and a silent audio output, so it never touches your own settings.
"""

import os
import shutil
import subprocess
import sys
import tempfile
import time
import warnings

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORK = tempfile.mkdtemp(prefix="samovar-lite-smoke-")
os.environ["XDG_CONFIG_HOME"] = os.path.join(WORK, "config")
sys.path.insert(0, ROOT)
if os.environ.get("WAYLAND_DISPLAY") and not os.environ.get("QT_QPA_PLATFORM"):
    os.environ["QT_QPA_PLATFORM"] = "wayland;xcb"

from PySide6.QtCore import QEventLoop, QMimeData, QPoint, QPointF, Qt, QTimer, QUrl
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from samovar_lite import skin
from samovar_lite.app import Player
from samovar_lite.settings import Settings

warnings.simplefilter("ignore", DeprecationWarning)
FAILED = []


def check(name, condition, detail=""):
    print(("PASS  " if condition else "FAIL  ") + name + (f"  ::  {detail}" if detail != "" and not condition else ""))
    if not condition:
        FAILED.append(name)


def wait(ms):
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def wait_until(condition, timeout=10.0):
    """Process events until `condition()` is true; returns whether it became true in time."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return True
        wait(50)
    return bool(condition())


def ffmpeg(*args):
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", *args], check=True, stdin=subprocess.DEVNULL)


def make_media():
    one, two = os.path.join(WORK, "Show.S01E01.mp4"), os.path.join(WORK, "Show.S01E02.mp4")
    ffmpeg(
        *("-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=24:duration=30"),
        *("-f", "lavfi", "-i", "sine=frequency=440:duration=30"),
        *("-c:v", "libx264", "-preset", "ultrafast", "-crf", "30", "-pix_fmt", "yuv420p"),
        *("-c:a", "aac", "-shortest", one),
    )
    ffmpeg(
        *("-f", "lavfi", "-i", "smptebars=size=960x540:rate=30:duration=8"),
        *("-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", two),
    )
    with open(os.path.join(WORK, "Show.S01E01.srt"), "w", encoding="utf-8") as fh:
        fh.write("1\n00:00:00,200 --> 00:00:29,000\nسلام — hello\n")
    legacy = os.path.join(WORK, "legacy.srt")
    with open(legacy, "wb") as fh:
        fh.write("1\n00:00:00,200 --> 00:00:29,000\nسلام دنبا\n".encode("cp1256"))
    return one, two, legacy


def stripes(player):
    """Counts abrupt light/dark row changes down the left edge of the frame (0-2 on a clean frame)."""
    image = player.video_area.video.grabFramebuffer()
    x = int(image.width() * 0.07)
    values = [image.pixelColor(x, y).lightness() for y in range(image.height())]
    return sum(1 for y in range(1, len(values)) if abs(values[y] - values[y - 1]) > 60)


def main():
    if not shutil.which("ffmpeg"):
        print("ffmpeg is required to generate the test clips")
        return 2
    one, two, legacy = make_media()
    app = QApplication(sys.argv[:1])
    app.setStyle("Fusion")
    app.setPalette(skin.dark_palette())
    app.setStyleSheet(skin.APP_QSS)
    p = Player(Settings(), silent=True)
    p.show()
    wait_until(lambda: p._gl_ready, 15)
    e = p.engine
    print(f"platform: {app.platformName()}, mpv: {e.get('mpv-version')}, renderer: {e.gl_renderer}")
    check("idle: logo shown, nothing loaded", p.video_area.logo.isVisible() and not p.has_file())

    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(one)])
    centre = QPointF(p.width() / 2, p.height() / 2)
    enter = QDragEnterEvent(centre.toPoint(), Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier)
    QApplication.sendEvent(p, enter)
    hint = p.video_area.osd.center_text
    check("drag over the window is accepted with a hint", enter.isAccepted() and hint == "Drop to play", hint)
    QApplication.sendEvent(p, QDropEvent(centre, Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier))
    started = wait_until(lambda: p._file_ready and p._last_pos > 1.0, 20)
    check("dropping a video plays it", started and p.current_path == one, (p.current_path, p._last_pos))
    if not started:
        print("engine messages:", list(e.log_lines)[-10:])
        p.close()
        print("\nFAILED: playback did not start, stopping here")
        return 1
    check("the next episode is queued", p.playlist.count() == 2, p.playlist.paths())
    fitted = wait_until(lambda: (p.video_area.width(), p.video_area.height()) == (1280, 720), 5)
    check("window resized to the video", fitted, (p.video_area.width(), p.video_area.height()))
    utf8 = wait_until(lambda: e.get("sub-text") == "سلام — hello", 5)
    check("subtitle next to the video loaded as UTF-8", utf8, e.get("sub-text"))

    QTest.keyClick(p, Qt.Key_Space)
    check("Space pauses", wait_until(lambda: e.get("pause") is True, 3))
    QTest.keyClick(p, Qt.Key_Space)
    wait_until(lambda: e.get("pause") is False, 3)
    before = p._last_pos
    QTest.keyClick(p, Qt.Key_Right)
    check("Right seeks 5 s", wait_until(lambda: 4 < p._last_pos - before < 9, 5), (before, p._last_pos))
    QTest.keyClick(p, Qt.Key_Down)
    check("Down lowers the volume", wait_until(lambda: e.get("volume") == 95, 3), e.get("volume"))
    QTest.keyClick(p, Qt.Key_Period)
    delayed = wait_until(lambda: abs(e.get("sub-delay") - 0.5) < 0.01, 3)
    check(". delays subtitles by 0.5 s", delayed, e.get("sub-delay"))
    QTest.keyClick(p, Qt.Key_Slash)

    p.open_paths([legacy])
    decoded = wait_until(lambda: (e.get("sub-text") or "").startswith("سلام د"), 5)
    check("Windows-1256 subtitle decoded as Persian", decoded, repr(e.get("sub-text")))

    QTest.keyClick(p, Qt.Key_Return)
    check("Enter goes full screen without chrome", wait_until(lambda: p.isFullScreen() and not p.ctrl.isVisible(), 5))
    wait(400)  # nobody leaves full screen in the same instant they entered it
    p._fs_mouse(QPoint(p.width() // 2, p.height() - 2))
    shown = wait_until(lambda: p.ctrl.isVisible() and p.seek.isVisible(), 3)
    check("pointer at the bottom edge shows the controls", shown)
    QTest.keyClick(p, Qt.Key_Escape)
    check("Esc leaves full screen", wait_until(lambda: not p.isFullScreen() and p.ctrl.isVisible(), 5))

    QTest.keyClick(p, Qt.Key_PageDown)
    switched = wait_until(lambda: p.current_path == two and p._file_ready and p._last_pos > 0.5, 20)
    check("PgDn plays the next file", switched, (p.current_path, p._last_pos))
    wait(500)
    check("picture is clean after switching resolution", stripes(p) <= 4, stripes(p))
    refit = wait_until(lambda: (p.video_area.width(), p.video_area.height()) == (960, 540), 5)
    check("window follows the new video size right after leaving full screen", refit, p.video_area.size())
    e.cmd("seek", 7.5, "absolute")
    stopped = wait_until(lambda: not p.has_file() and p.video_area.logo.isVisible(), 15)
    check("end of the playlist stops and shows the logo", stopped)

    p.play_row(0)
    wait_until(lambda: p._file_ready, 20)
    e.cmd("seek", 12, "absolute")
    wait_until(lambda: p._last_pos >= 12, 10)
    QTest.keyClick(p, Qt.Key_F4)
    wait_until(lambda: not p.has_file(), 5)
    QTest.keyClick(p, Qt.Key_Space)
    resumed = wait_until(lambda: p._file_ready and p._last_pos > 11, 20)
    check("playback position is remembered", resumed and p._last_pos < 20, p._last_pos)

    p.close()
    wait(300)
    check("settings were written", os.path.exists(os.path.join(WORK, "config", "samovar-lite", "settings.json")))
    shutil.rmtree(WORK, ignore_errors=True)
    print("\n" + ("ALL PASSED" if not FAILED else "FAILED: " + ", ".join(FAILED)))
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
