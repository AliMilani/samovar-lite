"""The right-click / title-button menu, rebuilt from live player state every time it opens."""

from __future__ import annotations

import os

from PySide6.QtGui import QActionGroup
from PySide6.QtWidgets import QMenu

from .util import fmt_time, title_of

LANGS = {
    "en": "English",
    "eng": "English",
    "fa": "Persian",
    "per": "Persian",
    "fas": "Persian",
    "ar": "Arabic",
    "ara": "Arabic",
    "fr": "French",
    "fre": "French",
    "fra": "French",
    "de": "German",
    "ger": "German",
    "deu": "German",
    "es": "Spanish",
    "spa": "Spanish",
    "it": "Italian",
    "ita": "Italian",
    "ru": "Russian",
    "rus": "Russian",
    "ja": "Japanese",
    "jpn": "Japanese",
    "ko": "Korean",
    "kor": "Korean",
    "zh": "Chinese",
    "chi": "Chinese",
    "zho": "Chinese",
    "tr": "Turkish",
    "tur": "Turkish",
    "pt": "Portuguese",
    "por": "Portuguese",
    "hi": "Hindi",
    "hin": "Hindi",
    "nl": "Dutch",
    "dut": "Dutch",
    "nld": "Dutch",
    "sv": "Swedish",
    "swe": "Swedish",
    "pl": "Polish",
    "pol": "Polish",
    "he": "Hebrew",
    "heb": "Hebrew",
    "el": "Greek",
    "gre": "Greek",
    "ell": "Greek",
    "uk": "Ukrainian",
    "ukr": "Ukrainian",
    "id": "Indonesian",
    "ind": "Indonesian",
    "th": "Thai",
    "tha": "Thai",
    "vi": "Vietnamese",
    "vie": "Vietnamese",
    "und": "Unknown",
}

ENCODINGS = [
    ("Auto-detect", "auto"),
    ("UTF-8", "utf-8"),
    ("Arabic / Persian (Windows-1256)", "cp1256"),
    ("Cyrillic (Windows-1251)", "cp1251"),
    ("Central European (Windows-1250)", "cp1250"),
    ("Western (Windows-1252)", "cp1252"),
    ("Greek (Windows-1253)", "cp1253"),
    ("Turkish (Windows-1254)", "cp1254"),
    ("Hebrew (Windows-1255)", "cp1255"),
    ("Chinese Simplified (GB18030)", "gb18030"),
    ("Chinese Traditional (Big5)", "big5"),
    ("Japanese (Shift-JIS)", "shift_jis"),
    ("Korean (CP949)", "cp949"),
]

ASPECTS = [
    ("Default", "-1"),
    ("4:3", "4:3"),
    ("16:9", "16:9"),
    ("16:10", "16:10"),
    ("1.85:1", "1.85"),
    ("2.35:1", "2.35"),
    ("2.39:1", "2.39"),
    ("1:1", "1"),
]
SPEEDS = [0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0, 3.0, 4.0]


def track_label(track: dict) -> str:
    lang = (track.get("lang") or "").lower()
    name = LANGS.get(lang) or (lang.upper() if lang else "")
    title = track.get("title") or ""
    if track.get("external") and track.get("external-filename"):
        title = os.path.basename(str(track["external-filename"]))
    parts = [p for p in (title, name) if p]
    label = "%d. %s" % (track.get("id", 0), " - ".join(parts) if parts else "Track")
    codec = track.get("codec")
    if codec:
        label += "  [%s]" % str(codec).upper()
    flags = [f for f in ("default", "forced", "external") if track.get(f)]
    if flags:
        label += "  (" + ", ".join(flags) + ")"
    return label.replace("&", "&&")


def _add(
    menu: QMenu,
    text: str,
    fn=None,
    key: str = "",
    checked=None,
    enabled: bool = True,
    group: QActionGroup | None = None,
):
    action = menu.addAction(text + ("      \t" + key if key else ""))
    if fn is not None:
        action.triggered.connect(lambda _=False: fn())
    if checked is not None:
        action.setCheckable(True)
        action.setChecked(bool(checked))
    if group is not None:
        group.addAction(action)
    action.setEnabled(enabled)
    return action


def _group(menu: QMenu) -> QActionGroup:
    group = QActionGroup(menu)
    group.setExclusive(True)
    return group


def add_tracks(menu: QMenu, p, kind: str, with_off: bool):
    tracks = [t for t in p.tracks() if t.get("type") == kind]
    group = _group(menu)
    if with_off:
        _add(
            menu,
            "Off",
            lambda: p.set_track(kind, "no"),
            checked=not any(t.get("selected") for t in tracks),
            group=group,
            enabled=p.has_file(),
        )
    for track in tracks:
        tid = track.get("id")
        _add(
            menu, track_label(track), lambda tid=tid: p.set_track(kind, tid), checked=track.get("selected"), group=group
        )
    if not tracks and not with_off:
        _add(menu, "(none)", enabled=False)


def build_main_menu(p) -> QMenu:
    has = p.has_file()
    s = p.settings
    root = QMenu(p)

    _add(root, "Open File(s)...", p.open_files_dialog, "F3")
    m = root.addMenu("Open")
    _add(m, "Open File(s)...", p.open_files_dialog, "Ctrl+O")
    _add(m, "Open Folder...", p.open_folder_dialog, "F2")
    _add(m, "Open URL...", p.open_url_dialog, "Ctrl+U")
    m.addSeparator()
    _add(m, "Load Subtitle...", p.load_subtitle_dialog, "Alt+O", enabled=has)
    _add(m, "Load External Audio...", p.load_audio_dialog, enabled=has)
    recent = root.addMenu("Recent Files")
    for i, path in enumerate(s["recent"][:20], 1):
        action = _add(recent, "%d. %s" % (i, title_of(path).replace("&", "&&")), lambda path=path: p.open_paths([path]))
        action.setToolTip(path)
    if s["recent"]:
        recent.addSeparator()
    _add(recent, "Clear Recent Files", p.clear_recent, enabled=bool(s["recent"]))
    _add(root, "Close Playback", p.stop, "F4", enabled=has)
    root.addSeparator()

    # -- Playback --------------------------------------------------------------------------------
    m = root.addMenu("Playback")
    _add(m, "Play / Pause", p.toggle_pause, "Space", enabled=has or p.playlist.count() > 0)
    _add(m, "Stop", p.stop, "F4", enabled=has)
    _add(m, "Previous File", p.prev_file, "PgUp", enabled=p.playlist.count() > 1)
    _add(m, "Next File", p.next_file, "PgDn", enabled=p.playlist.count() > 1)
    m.addSeparator()
    j = m.addMenu("Jump")
    j.setEnabled(has)
    for label, key, amount in (
        ("Back %d sec" % s["seek_small"], "Left", -s["seek_small"]),
        ("Forward %d sec" % s["seek_small"], "Right", s["seek_small"]),
        ("Back %d sec" % s["seek_medium"], "Ctrl+Left", -s["seek_medium"]),
        ("Forward %d sec" % s["seek_medium"], "Ctrl+Right", s["seek_medium"]),
        ("Back %d sec" % s["seek_large"], "Shift+Left", -s["seek_large"]),
        ("Forward %d sec" % s["seek_large"], "Shift+Right", s["seek_large"]),
        ("Back %d sec" % s["seek_huge"], "Ctrl+Alt+Left", -s["seek_huge"]),
        ("Forward %d sec" % s["seek_huge"], "Ctrl+Alt+Right", s["seek_huge"]),
    ):
        _add(j, label, lambda amount=amount: p.seek_rel(amount), key)
    j.addSeparator()
    _add(j, "Jump to Beginning", lambda: p.seek_abs(0), "Backspace")
    _add(j, "Go to Time...", p.go_to_dialog, "G")
    j.addSeparator()
    _add(j, "Previous Subtitle Line", lambda: p.sub_seek(-1))
    _add(j, "Next Subtitle Line", lambda: p.sub_seek(1))
    sp = m.addMenu("Speed")
    _add(sp, "Faster", lambda: p.change_speed(0.1), "C")
    _add(sp, "Slower", lambda: p.change_speed(-0.1), "X")
    _add(sp, "Normal", lambda: p.set_speed(1.0), "Z")
    sp.addSeparator()
    group = _group(sp)
    speed = p.state.get("speed") or 1.0
    for value in SPEEDS:
        _add(sp, "%gx" % value, lambda value=value: p.set_speed(value), checked=abs(speed - value) < 0.005, group=group)
    fr = m.addMenu("Frame Step")
    fr.setEnabled(has)
    _add(fr, "Next Frame", lambda: p.frame_step(1), "F")
    _add(fr, "Previous Frame", lambda: p.frame_step(-1), "D")
    ab = m.addMenu("A-B Repeat")
    ab.setEnabled(has)
    a, b = p.state.get("ab-loop-a"), p.state.get("ab-loop-b")
    a = a if isinstance(a, (int, float)) else None
    b = b if isinstance(b, (int, float)) else None
    _add(ab, "Set Start Point (A)" + ("   " + fmt_time(a) if a is not None else ""), lambda: p.ab_set("a"), "[")
    _add(ab, "Set End Point (B)" + ("   " + fmt_time(b) if b is not None else ""), lambda: p.ab_set("b"), "]")
    ab.addSeparator()
    _add(ab, "Clear A-B Repeat", p.ab_clear, "\\", enabled=a is not None or b is not None)
    chapters = p.state.get("chapter-list") or []
    if chapters:
        ch = m.addMenu("Chapters")
        current = p.engine.get("chapter", -1)
        group = _group(ch)
        for i, chapter in enumerate(chapters):
            title = str(chapter.get("title") or "Chapter %d" % (i + 1)).replace("&", "&&")
            _add(
                ch,
                "%d. %s   %s" % (i + 1, title, fmt_time(chapter.get("time", 0))),
                lambda i=i: p.set_chapter(i),
                checked=i == current,
                group=group,
            )
        ch.addSeparator()
        _add(ch, "Previous Chapter", lambda: p.chapter_step(-1), "Shift+PgUp")
        _add(ch, "Next Chapter", lambda: p.chapter_step(1), "Shift+PgDn")
    m.addSeparator()
    rp = m.addMenu("Repeat")
    group = _group(rp)
    for label, mode in (("Off", "off"), ("Current File", "one"), ("Playlist", "all")):
        _add(rp, label, lambda mode=mode: p.set_repeat(mode), checked=s["repeat"] == mode, group=group)
    _add(m, "Shuffle", p.toggle_shuffle, checked=s["shuffle"])
    _add(m, "Remember Playback Position", p.toggle_resume, checked=s["resume"])

    # -- Subtitles -------------------------------------------------------------------------------
    m = root.addMenu("Subtitles")
    _add(m, "Show Subtitles", p.toggle_sub_visibility, "Alt+H", checked=p.state.get("sub-visibility", True))
    _add(m, "Load Subtitle...", p.load_subtitle_dialog, "Alt+O", enabled=has)
    m.addSeparator()
    add_tracks(m, p, "sub", with_off=True)
    m.addSeparator()
    sec = m.addMenu("Secondary Subtitle")
    sec.setEnabled(has)
    subs = [t for t in p.tracks() if t.get("type") == "sub"]
    second = p.engine.get("secondary-sid", False) if has else False
    group = _group(sec)
    _add(sec, "Off", lambda: p.set_secondary_sub("no"), checked=not second, group=group)
    for track in subs:
        tid = track.get("id")
        _add(sec, track_label(track), lambda tid=tid: p.set_secondary_sub(tid), checked=second == tid, group=group)
    sy = m.addMenu("Subtitle Sync")
    sy.setEnabled(has)
    _add(sy, "0.5 sec Faster", lambda: p.sub_delay(-0.5), ",")
    _add(sy, "0.5 sec Slower", lambda: p.sub_delay(0.5), ".")
    _add(sy, "Reset Sync", lambda: p.sub_delay(None), "/")
    sz = m.addMenu("Size and Position")
    _add(sz, "Larger", lambda: p.sub_scale(0.1), "Alt+PgUp")
    _add(sz, "Smaller", lambda: p.sub_scale(-0.1), "Alt+PgDn")
    _add(sz, "Move Up", lambda: p.sub_move(-1), "Alt+Up")
    _add(sz, "Move Down", lambda: p.sub_move(1), "Alt+Down")
    sz.addSeparator()
    _add(sz, "Reset", p.sub_reset)
    en = m.addMenu("Encoding")
    group = _group(en)
    for label, codepage in ENCODINGS:
        _add(
            en,
            label,
            lambda codepage=codepage: p.set_sub_codepage(codepage),
            checked=s["sub_codepage"] == codepage,
            group=group,
        )
    m.addSeparator()
    _add(m, "Subtitle Settings...", lambda: p.show_preferences("Subtitles"))

    # -- Video -----------------------------------------------------------------------------------
    m = root.addMenu("Video")
    ar = m.addMenu("Aspect Ratio")
    group = _group(ar)
    for label, value in ASPECTS:
        _add(
            ar,
            label,
            lambda label=label, value=value: p.set_aspect(label, value),
            checked=p.aspect_name == label,
            group=group,
        )
    dm = m.addMenu("Frame Size")
    group = _group(dm)
    for label, mode in (
        ("Keep Aspect Ratio", "fit"),
        ("Fill Window (Crop)", "fill"),
        ("Stretch to Window", "stretch"),
        ("Original Size", "original"),
    ):
        _add(dm, label, lambda mode=mode: p.set_display_mode(mode), checked=p.display_mode == mode, group=group)
    zm = m.addMenu("Pan && Scan")
    _add(zm, "Zoom In", lambda: p.zoom(0.1), "Num 9")
    _add(zm, "Zoom Out", lambda: p.zoom(-0.1), "Num 1")
    zm.addSeparator()
    _add(zm, "Move Left", lambda: p.pan(-0.02, 0), "Num 4")
    _add(zm, "Move Right", lambda: p.pan(0.02, 0), "Num 6")
    _add(zm, "Move Up", lambda: p.pan(0, -0.02), "Num 8")
    _add(zm, "Move Down", lambda: p.pan(0, 0.02), "Num 2")
    zm.addSeparator()
    _add(zm, "Reset", p.reset_geometry, "Num 5")
    ro = m.addMenu("Rotate and Flip")
    group = _group(ro)
    rotation = int(p.engine.get("video-rotate", 0) or 0)
    for degrees in (0, 90, 180, 270):
        _add(ro, "%d°" % degrees, lambda degrees=degrees: p.rotate(degrees), checked=rotation == degrees, group=group)
    ro.addSeparator()
    _add(ro, "Rotate 90° Clockwise", lambda: p.rotate(None), "Alt+K")
    _add(ro, "Flip Horizontally", lambda: p.toggle_flip("hflip"), "Ctrl+Z", checked=p.flips["hflip"])
    _add(ro, "Flip Vertically", lambda: p.toggle_flip("vflip"), "Ctrl+V", checked=p.flips["vflip"])
    im = m.addMenu("Image Adjustments")
    for label, prop, minus, plus in (
        ("Brightness", "brightness", "W", "E"),
        ("Contrast", "contrast", "R", "T"),
        ("Saturation", "saturation", "Y", "U"),
        ("Hue", "hue", "I", "O"),
    ):
        _add(im, label + " -", lambda prop=prop: p.image_adjust(prop, -1), minus)
        _add(im, label + " +", lambda prop=prop: p.image_adjust(prop, 1), plus)
    im.addSeparator()
    _add(im, "Reset", p.image_reset, "Q")
    m.addSeparator()
    _add(m, "Deinterlace", p.toggle_deinterlace, checked=bool(p.engine.get("deinterlace", False)))
    hw = m.addMenu("Hardware Acceleration")
    group = _group(hw)
    _add(hw, "Use Hardware Decoding", lambda: p.set_hwdec(True), checked=s["hwdec"], group=group)
    _add(hw, "Software Decoding", lambda: p.set_hwdec(False), checked=not s["hwdec"], group=group)
    hw.addSeparator()
    active = p.state.get("hwdec-current") or "no"
    _add(hw, "Active: " + ("none (software)" if active == "no" else str(active)), enabled=False)
    videos = [t for t in p.tracks() if t.get("type") == "video" and not t.get("albumart")]
    if len(videos) > 1:
        vt = m.addMenu("Video Track")
        add_tracks(vt, p, "video", with_off=False)

    # -- Audio -----------------------------------------------------------------------------------
    m = root.addMenu("Audio")
    st = m.addMenu("Select Audio Stream")
    add_tracks(st, p, "audio", with_off=False)
    _add(m, "Load External Audio...", p.load_audio_dialog, enabled=has)
    m.addSeparator()
    _add(m, "Volume Up", lambda: p.volume_step(1), "Up")
    _add(m, "Volume Down", lambda: p.volume_step(-1), "Down")
    _add(m, "Mute", p.toggle_mute, "M", checked=bool(p.state.get("mute")))
    m.addSeparator()
    sy = m.addMenu("Audio Sync")
    sy.setEnabled(has)
    _add(sy, "0.05 sec Faster", lambda: p.audio_delay(-0.05), "Shift+,")
    _add(sy, "0.05 sec Slower", lambda: p.audio_delay(0.05), "Shift+.")
    _add(sy, "Reset Sync", lambda: p.audio_delay(None), "Shift+/")
    dv = m.addMenu("Output Device")
    group = _group(dv)
    current = p.engine.get("audio-device", "auto")
    for device in p.engine.get("audio-device-list", []) or []:
        name = device.get("name")
        label = str(device.get("description") or name).replace("&", "&&")
        if name == "auto":
            label = "Auto (system default)"
        _add(dv, label, lambda name=name: p.set_audio_device(name), checked=name == current, group=group)
    _add(m, "Normalize Volume", p.toggle_normalize, checked=p.normalize)
    _add(m, "Equalizer...", lambda: p.show_control_panel("Audio"), "F7")

    # -- Misc ------------------------------------------------------------------------------------
    m = root.addMenu("Misc")
    _add(m, "Save Current Frame", lambda: p.screenshot("video"), "Ctrl+E", enabled=has)
    _add(m, "Save Current Frame (With Subtitles)", lambda: p.screenshot("subtitles"), "Ctrl+Alt+E", enabled=has)
    _add(m, "Copy Current Frame", lambda: p.screenshot("video", True), "Ctrl+C", enabled=has)
    _add(m, "Copy Current Frame (With Subtitles)", lambda: p.screenshot("subtitles", True), "Ctrl+Alt+C", enabled=has)
    _add(m, "Open Screenshot Folder", p.open_screenshot_folder)
    m.addSeparator()
    ot = m.addMenu("On Top")
    group = _group(ot)
    for label, mode in (("Never", "never"), ("Always", "always"), ("While Playing", "playing")):
        _add(ot, label, lambda mode=mode: p.set_on_top(mode), checked=s["on_top"] == mode, group=group)
    _add(m, "Playback Information (OSD)", p.toggle_info, "Tab", checked=p.info_visible)
    root.addSeparator()

    ws = root.addMenu("Window Size")
    for pct, key in ((50, "1"), (100, "2"), (150, "3"), (200, "4")):
        _add(ws, "%d%%" % pct, lambda pct=pct: p.set_window_scale(pct), key, enabled=has)
    ws.addSeparator()
    _add(ws, "Fit Window to Video on Open", p.toggle_autofit, checked=s["autofit"])
    _add(root, "Full Screen", p.toggle_fullscreen, "Enter", checked=p.isFullScreen())
    root.addSeparator()
    _add(root, "Preferences...", p.show_preferences, "F5")
    _add(root, "Playlist...", p.toggle_playlist, "F6", checked=p.playlist_visible)
    _add(root, "Control Panel...", p.show_control_panel, "F7")
    _add(root, "Playback/System Info...", p.show_media_info, "Ctrl+F1")
    _add(root, "About...", p.show_about, "F1")
    root.addSeparator()
    _add(root, "Exit", p.quit, "Alt+F4")
    return root


def build_track_menu(p, kind: str) -> QMenu:
    menu = QMenu(p)
    add_tracks(menu, p, kind, with_off=kind == "sub")
    if kind == "sub":
        menu.addSeparator()
        _add(menu, "Load Subtitle...", p.load_subtitle_dialog, "Alt+O", enabled=p.has_file())
    return menu
