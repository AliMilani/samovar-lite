"""Small helpers: time formatting, media file detection, natural sorting."""

from __future__ import annotations

import os
import re

VIDEO_EXT = {
    ".mkv",
    ".mp4",
    ".m4v",
    ".avi",
    ".mov",
    ".wmv",
    ".flv",
    ".webm",
    ".ts",
    ".m2ts",
    ".mts",
    ".mpg",
    ".mpeg",
    ".vob",
    ".3gp",
    ".ogv",
    ".rm",
    ".rmvb",
    ".asf",
    ".divx",
    ".f4v",
    ".mxf",
    ".dat",
    ".tp",
    ".trp",
    ".wtv",
    ".y4m",
    ".gif",
}
AUDIO_EXT = {
    ".mp3",
    ".flac",
    ".m4a",
    ".aac",
    ".ogg",
    ".oga",
    ".opus",
    ".wav",
    ".wma",
    ".ac3",
    ".dts",
    ".ape",
    ".mka",
    ".aiff",
    ".alac",
    ".amr",
    ".wv",
    ".tta",
    ".mpc",
}
SUB_EXT = {".srt", ".ass", ".ssa", ".sub", ".vtt", ".smi", ".idx", ".sup", ".txt", ".lrc", ".ttml"}
PLAYLIST_EXT = {".m3u", ".m3u8", ".pls", ".cue"}
MEDIA_EXT = VIDEO_EXT | AUDIO_EXT

MEDIA_FILTER = "Media files (" + " ".join("*" + e for e in sorted(MEDIA_EXT | PLAYLIST_EXT)) + ");;All files (*)"
SUB_FILTER = "Subtitles (" + " ".join("*" + e for e in sorted(SUB_EXT)) + ");;All files (*)"


def ext(path: str) -> str:
    return os.path.splitext(path)[1].lower()


def is_url(path: str) -> bool:
    return bool(re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", path))


def is_media(path: str) -> bool:
    return ext(path) in MEDIA_EXT


def is_sub(path: str) -> bool:
    return ext(path) in SUB_EXT and ext(path) != ".txt"


def natural_key(text: str):
    return [int(t) if t.isdigit() else t.casefold() for t in re.split(r"(\d+)", text)]


def fmt_time(seconds) -> str:
    try:
        total = max(0, int(seconds))
    except (TypeError, ValueError):
        total = 0
    return "%02d:%02d:%02d" % (total // 3600, total % 3600 // 60, total % 60)


def fmt_signed(seconds: float, digits: int = 1) -> str:
    return ("%+." + str(digits) + "f sec") % seconds


def parse_time(text: str, duration: float | None = None):
    """Accepts HH:MM:SS(.mmm), MM:SS, plain seconds or NN%. Returns seconds or None."""
    text = text.strip()
    if not text:
        return None
    try:
        if text.endswith("%"):
            if not duration:
                return None
            return max(0.0, min(100.0, float(text[:-1]))) / 100.0 * duration
        parts = [float(p) for p in text.split(":")]
    except ValueError:
        return None
    if len(parts) > 3:
        return None
    value = 0.0
    for part in parts:
        value = value * 60 + part
    return value


def title_of(path: str) -> str:
    if is_url(path):
        return path
    return os.path.basename(path) or path


def folder_media(folder: str) -> list[str]:
    try:
        names = [n for n in os.listdir(folder) if is_media(n)]
    except OSError:
        return []
    names.sort(key=natural_key)
    return [os.path.join(folder, n) for n in names]


def expand_paths(paths: list[str]) -> list[str]:
    """Folders become their media files (recursively); files and URLs pass through."""
    out: list[str] = []
    for path in paths:
        if is_url(path):
            out.append(path)
        elif os.path.isdir(path):
            for root, dirs, files in os.walk(path):
                dirs.sort(key=natural_key)
                for name in sorted(files, key=natural_key):
                    if is_media(name):
                        out.append(os.path.join(root, name))
        else:
            out.append(os.path.abspath(path))
    return out


def human_size(num) -> str:
    try:
        num = float(num)
    except (TypeError, ValueError):
        return ""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if num < 1024 or unit == "TB":
            return ("%d %s" % (num, unit)) if unit == "B" else ("%.1f %s" % (num, unit))
        num /= 1024
    return ""


def similar_files(path: str) -> list[str]:
    """Files that belong with `path`, like "add similar files" in PotPlayer (episodes, album tracks)."""
    folder, name = os.path.split(path)
    kind = VIDEO_EXT if ext(name) in VIDEO_EXT else AUDIO_EXT if ext(name) in AUDIO_EXT else None
    if kind is None:
        return [path]

    def skeleton(filename: str) -> str:
        return re.sub(r"\d+", "#", os.path.splitext(filename)[0].casefold())

    target = skeleton(name)
    try:
        names = [n for n in os.listdir(folder) if ext(n) in kind]
    except OSError:
        return [path]
    if kind is VIDEO_EXT:
        names = [n for n in names if skeleton(n) == target] if "#" in target else [name]
    if name not in names:
        names.append(name)
    names.sort(key=natural_key)
    return [os.path.join(folder, n) for n in names]


def read_playlist_file(path: str) -> list[str]:
    """Minimal .m3u/.m3u8/.pls reader; relative entries resolve against the playlist's folder."""
    entries: list[str] = []
    base = os.path.dirname(os.path.abspath(path))
    try:
        with open(path, encoding="utf-8-sig", errors="replace") as fh:
            lines = fh.read().splitlines()
    except OSError:
        return entries
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("["):
            continue
        if ext(path) == ".pls":
            if not line.lower().startswith("file") or "=" not in line:
                continue
            line = line.split("=", 1)[1].strip()
        if not is_url(line) and not os.path.isabs(line):
            line = os.path.join(base, line)
        entries.append(line)
    return entries
