"""libmpv engine: library loading, a property/command facade and the OpenGL video widget."""

from __future__ import annotations

import collections
import ctypes.util
import locale
import os
import sys
from pathlib import Path

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QOpenGLContext
from PySide6.QtOpenGL import QOpenGLFramebufferObject
from PySide6.QtOpenGLWidgets import QOpenGLWidget

# Source checkouts may carry a libmpv unpacked by install.sh; SAMOVAR_LITE_LIBMPV overrides both.
_VENDORED = Path(
    os.environ.get("SAMOVAR_LITE_LIBMPV")
    or Path(__file__).resolve().parent.parent / "vendor/libmpv/usr/lib/x86_64-linux-gnu/libmpv.so.2"
)

OBSERVED = (
    "time-pos",
    "duration",
    "pause",
    "volume",
    "mute",
    "speed",
    "track-list",
    "chapter-list",
    "media-title",
    "path",
    "idle-active",
    "eof-reached",
    "hwdec-current",
    "video-params",
    "sub-delay",
    "audio-delay",
    "sub-visibility",
    "paused-for-cache",
    "cache-buffering-state",
    "demuxer-cache-time",
    "ab-loop-a",
    "ab-loop-b",
    "seeking",
)


def import_mpv():
    """Import python-mpv, falling back to the libmpv bundled under vendor/ when none is installed."""
    original = ctypes.util.find_library

    def find(name):
        if name != "mpv":
            return original(name)
        if os.environ.get("SAMOVAR_LITE_LIBMPV") and _VENDORED.exists():
            return str(_VENDORED)
        return original(name) or (str(_VENDORED) if _VENDORED.exists() else None)

    ctypes.util.find_library = find
    try:
        # Qt switches LC_NUMERIC to the user's locale; libmpv refuses to start unless it is "C".
        locale.setlocale(locale.LC_NUMERIC, "C")
        import mpv
    finally:
        ctypes.util.find_library = original
    return mpv


class Engine(QObject):
    """Thin, crash-safe wrapper around one mpv core. All signals arrive on the GUI thread."""

    prop = Signal(str, object)
    event = Signal(str, object)

    def __init__(self, settings, silent: bool = False, verbose: bool = False, parent=None):
        super().__init__(parent)
        self.lib = import_mpv()
        self.verbose = verbose
        self.log_lines = collections.deque(maxlen=200)
        options = {
            "vo": "libmpv",
            "idle": "yes",
            "keep_open": "yes",
            "osc": False,
            "osd_level": 0,
            "input_default_bindings": False,
            "input_vo_keyboard": False,
            "hwdec": self.hwdec_value(settings["hwdec"]),
            "hr_seek": "yes",
            "volume_max": 100,
            "volume": max(0, min(100, int(settings["volume"]))),
            "mute": bool(settings["mute"]),
            "audio_client_name": "Samovar Lite",
            "screenshot_format": "png",
            "sub_auto": settings["sub_auto"],
            "sub_file_paths": "sub:subs:Sub:Subs:subtitles:Subtitles",
            "sub_codepage": settings["sub_codepage"],
            "sub_font_size": settings["sub_size"],
            "sub_bold": bool(settings["sub_bold"]),
            "sub_pos": settings["sub_pos"],
            "sub_visibility": bool(settings["sub_visible"]),
            "sub_fix_timing": True,
            "slang": settings["preferred_sub_lang"],
            "alang": settings["preferred_audio_lang"],
            "audio_display": "embedded-first",
            "reset_on_next_file": "sub-delay,audio-delay,video-zoom,video-pan-x,video-pan-y,"
            "video-rotate,video-aspect-override,ab-loop-a,ab-loop-b",
            "ytdl": True,
        }
        if settings["sub_font"]:
            options["sub_font"] = settings["sub_font"]
        if silent:
            options["ao"] = "null"
        level = os.environ.get("SAMOVAR_LITE_LOGLEVEL") or ("v" if verbose else "warn")
        try:
            self.mpv = self.lib.MPV(log_handler=self._on_log, loglevel=level, **options)
        except Exception:
            # Builds without Lua or yt-dlp support reject these; everything else is mandatory.
            for optional in ("osc", "ytdl"):
                options.pop(optional, None)
            self.mpv = self.lib.MPV(log_handler=self._on_log, loglevel=level, **options)
        for name in OBSERVED:
            self.mpv.observe_property(name, self._on_property)
        self.mpv.register_event_callback(self._on_event)
        self._alive = True

    # -- callbacks from mpv's event thread --------------------------------------------------------
    def _on_property(self, name, value):
        self.prop.emit(name, value)

    def _on_event(self, event):
        try:
            data = event.as_dict(decoder=self.lib.lazy_decoder)
        except Exception:
            return
        name = data.get("event")
        if name in ("file-loaded", "end-file", "start-file", "playback-restart", "video-reconfig"):
            self.event.emit(name, data)

    def _on_log(self, level, component, message):
        line = "[%s] %s: %s" % (level, component, message.strip())
        self.log_lines.append(line)
        if self.verbose:
            print(line, file=sys.stderr)

    # -- facade ----------------------------------------------------------------------------------
    # Decode on the GPU that also draws the window: on hybrid laptops this keeps the second GPU asleep.
    gl_renderer = ""

    @classmethod
    def hwdec_value(cls, enabled: bool) -> str:
        # Copy-back decoders work with any render surface (X11, Wayland, any GPU vendor).
        if not enabled:
            return "no"
        if "nvidia" in cls.gl_renderer.lower():
            return "nvdec-copy,vaapi-copy,auto-copy-safe"
        return "vaapi-copy,nvdec-copy,auto-copy-safe"

    def apply_renderer_workarounds(self):
        """Avoid scalers that need lookup textures on Mesa's Intel driver.

        There (seen with Mesa 26 on Raptor Lake) the lookup texture of a scaler can come up with
        garbage when the scaler is rebuilt for a new video size after subtitles were drawn, which
        shows as black horizontal stripes over the picture. The fixed-function scalers are not
        affected. Set SAMOVAR_LITE_NO_GPU_WORKAROUNDS=1 to keep mpv's default scalers.
        """
        if os.environ.get("SAMOVAR_LITE_NO_GPU_WORKAROUNDS") or "intel" not in self.gl_renderer.lower():
            return
        workarounds = (
            ("scale", "bicubic_fast"),
            ("cscale", "bicubic_fast"),
            ("dscale", "bilinear"),
            ("correct-downscaling", "no"),  # needs a lookup-table scaler, and warns without one
        )
        for option, value in workarounds:
            self.set(option, value)

    def get(self, name: str, default=None):
        if not self._alive:
            return default
        try:
            value = self.mpv._get_property(name, self.lib.lazy_decoder)
        except Exception:
            return default
        return default if value is None else value

    def set(self, name: str, value) -> bool:
        if not self._alive:
            return False
        try:
            self.mpv._set_property(name, value)
            return True
        except Exception as exc:
            self.log_lines.append("[set] %s=%r: %s" % (name, value, exc))
            return False

    def cmd(self, *args) -> bool:
        """Queue a command asynchronously (never blocks the GUI thread)."""
        if not self._alive:
            return False
        try:
            self.mpv.command_async(*[str(a) for a in args])
            return True
        except Exception as exc:
            self.log_lines.append("[cmd] %r: %s" % (args, exc))
            return False

    def load(self, path: str, start: float | None = None) -> bool:
        """Replace the current file, optionally starting at `start` seconds."""
        if not start:
            return self.cmd("loadfile", path, "replace")
        option = "start=%.2f" % start
        if tuple(self.mpv.mpv_version_tuple) >= (0, 38):
            return self.cmd("loadfile", path, "replace", "-1", option)  # 0.38 added an index argument
        return self.cmd("loadfile", path, "replace", option)

    def cmd_sync(self, *args):
        if not self._alive:
            return None
        try:
            return self.mpv.command(*[str(a) for a in args])
        except Exception as exc:
            self.log_lines.append("[cmd] %r: %s" % (args, exc))
            return None

    def add(self, name: str, delta: float, lo: float | None = None, hi: float | None = None):
        value = self.get(name, 0) or 0
        value += delta
        if lo is not None:
            value = max(lo, value)
        if hi is not None:
            value = min(hi, value)
        self.set(name, value)
        return value

    def shutdown(self):
        if not self._alive:
            return
        self._alive = False
        try:
            self.mpv.terminate()
        except Exception:
            pass


def _gl_proc_address(_ctx, name):
    context = QOpenGLContext.currentContext()
    if context is None:
        return 0
    try:
        return int(context.getProcAddress(name))
    except Exception:
        return 0


class VideoWidget(QOpenGLWidget):
    """Draws mpv's output into Qt's framebuffer, so ordinary widgets can be stacked on top."""

    frameRequested = Signal()
    ready = Signal()

    def __init__(self, engine: Engine, parent=None):
        super().__init__(parent)
        self.engine = engine
        self.ctx = None
        self._closed = False
        self._proc = engine.lib.MpvGlGetProcAddressFn(_gl_proc_address)
        self.frameRequested.connect(self.update, Qt.QueuedConnection)
        self.frameSwapped.connect(self._swapped)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.NoFocus)

    def initializeGL(self):
        if self.ctx is not None or self._closed:
            return
        lib = self.engine.lib
        self.ctx = lib.MpvRenderContext(self.engine.mpv, "opengl", opengl_init_params={"get_proc_address": self._proc})
        self.ctx.update_cb = self.frameRequested.emit
        self.context().aboutToBeDestroyed.connect(self.release)
        try:
            renderer = self.context().functions().glGetString(0x1F01)  # GL_RENDERER
            Engine.gl_renderer = renderer.decode() if isinstance(renderer, bytes) else str(renderer or "")
        except Exception:
            Engine.gl_renderer = ""
        if self.engine.get("hwdec", "no") != "no":
            self.engine.set("hwdec", Engine.hwdec_value(True))
        self.engine.apply_renderer_workarounds()
        self.ready.emit()

    def paintGL(self):
        if self.ctx is None:
            return
        ratio = self.devicePixelRatioF()
        self.ctx.render(
            flip_y=True,
            opengl_fbo={
                "w": max(1, int(round(self.width() * ratio))),
                "h": max(1, int(round(self.height() * ratio))),
                "fbo": self.defaultFramebufferObject(),
            },
        )
        # mpv leaves framebuffer 0 bound; Qt expects its own one for the work it does after paintGL.
        QOpenGLFramebufferObject.bindDefault()

    def _swapped(self):
        if self.ctx is not None:
            self.ctx.report_swap()

    def release(self):
        if self.ctx is None:
            return
        ctx, self.ctx = self.ctx, None
        try:
            self.makeCurrent()
            ctx.update_cb = None
            ctx.free()
            self.doneCurrent()
        except Exception:
            pass

    def shutdown(self):
        """Final teardown: stop painting for good, then free the render context."""
        self._closed = True
        self.setUpdatesEnabled(False)
        try:
            self.frameRequested.disconnect(self.update)
        except (RuntimeError, TypeError):
            pass
        self.release()
