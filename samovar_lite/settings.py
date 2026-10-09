"""Persistent settings stored as one JSON file under ~/.config/samovar-lite."""

from __future__ import annotations

import json
import os
import tempfile

CONFIG_DIR = os.path.join(os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config"), "samovar-lite")
CONFIG_FILE = os.path.join(CONFIG_DIR, "settings.json")
# Settings written before the project was renamed; read once if the new file does not exist yet.
LEGACY_FILE = os.path.join(os.path.dirname(CONFIG_DIR), "fast-pot-player", "settings.json")

DEFAULTS = {
    "volume": 100,
    "mute": False,
    "window_w": 806,
    "window_h": 546,
    "window_x": None,
    "window_y": None,
    "playlist_visible": False,
    "playlist_width": 280,
    "on_top": "never",  # never | always | playing
    "use_x11": False,
    "autofit": True,
    "autofit_max_pct": 85,
    "resume": True,
    "show_remaining": False,
    "repeat": "off",  # off | one | all
    "shuffle": False,
    "seek_small": 5,
    "seek_medium": 30,
    "seek_large": 60,
    "seek_huge": 300,
    "volume_step": 5,
    "hwdec": True,
    "sub_font": "",
    "sub_size": 44,
    "sub_bold": True,
    "sub_codepage": "cp1256",  # used only when a file is not valid UTF-8
    "sub_auto": "fuzzy",
    "sub_pos": 100,
    "sub_visible": True,
    "preferred_sub_lang": "",
    "preferred_audio_lang": "",
    "screenshot_dir": "",
    "last_dir": "",
    "last_sub_dir": "",
    "recent": [],
    "positions": {},
    "eq": [0] * 10,
    "eq_enabled": False,
    "first_run": True,
}


class Settings:
    def __init__(self, path: str = CONFIG_FILE):
        self.path = path
        self.data = dict(DEFAULTS)
        source = path
        if path == CONFIG_FILE and not os.path.exists(path) and os.path.exists(LEGACY_FILE):
            source = LEGACY_FILE
        try:
            with open(source, encoding="utf-8") as fh:
                loaded = json.load(fh)
            if isinstance(loaded, dict):
                self.data.update(loaded)
            self.data["sub_codepage"] = str(self.data.get("sub_codepage") or "auto").lstrip("+")
        except (OSError, ValueError):
            pass

    def __getitem__(self, key):
        return self.data.get(key, DEFAULTS.get(key))

    def __setitem__(self, key, value):
        self.data[key] = value

    def save(self):
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=os.path.dirname(self.path), prefix=".settings-")
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(self.data, fh, ensure_ascii=False, indent=1)
            os.replace(tmp, self.path)
        except OSError:
            pass

    # -- recent files and resume positions ------------------------------------------------------
    def add_recent(self, path: str):
        recent = [p for p in self.data.get("recent", []) if p != path]
        recent.insert(0, path)
        self.data["recent"] = recent[:20]

    def set_position(self, path: str, seconds: float | None):
        positions = self.data.setdefault("positions", {})
        positions.pop(path, None)
        if seconds is not None:
            positions[path] = round(float(seconds), 1)
            while len(positions) > 300:
                positions.pop(next(iter(positions)))

    def get_position(self, path: str):
        return self.data.get("positions", {}).get(path)
