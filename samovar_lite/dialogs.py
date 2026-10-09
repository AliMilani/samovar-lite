"""Dialogs: go-to-time, open URL, control panel, preferences, media information, about."""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QGuiApplication
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFontComboBox,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSlider,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from . import skin
from .menus import ENCODINGS
from .util import fmt_time, is_url, parse_time

EQ_FREQS = [31, 62, 125, 250, 500, 1000, 2000, 4000, 8000, 16000]
EQ_PRESETS = {
    "Flat": [0] * 10,
    "Bass Boost": [7, 6, 5, 3, 1, 0, 0, 0, 0, 0],
    "Treble Boost": [0, 0, 0, 0, 0, 1, 3, 5, 6, 7],
    "Vocal": [-3, -2, 0, 2, 4, 4, 3, 1, 0, -1],
    "Rock": [5, 4, 2, 0, -1, -1, 1, 3, 4, 5],
    "Pop": [-1, 0, 2, 4, 4, 2, 0, -1, -1, -1],
    "Classical": [4, 3, 2, 1, 0, 0, 0, 1, 2, 3],
    "Movie": [4, 3, 1, 0, 1, 2, 3, 2, 1, 1],
}


class GoToDialog(QDialog):
    def __init__(self, parent, position: float, duration: float):
        super().__init__(parent)
        self.setWindowTitle("Go to Time")
        self.duration = duration
        self.value = None
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Time (HH:MM:SS, MM:SS, seconds or NN%):"))
        self.edit = QLineEdit(fmt_time(position))
        self.edit.selectAll()
        layout.addWidget(self.edit)
        hint = QLabel("Current: %s / %s" % (fmt_time(position), fmt_time(duration)))
        hint.setStyleSheet("color: #8c8c8c;")
        layout.addWidget(hint)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.setFixedWidth(320)

    def _accept(self):
        value = parse_time(self.edit.text(), self.duration)
        if value is None:
            self.edit.selectAll()
            return
        self.value = max(0.0, min(value, self.duration) if self.duration else value)
        self.accept()


class UrlDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("Open URL")
        self.url = None
        self.append = False
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Address:"))
        self.edit = QLineEdit()
        clip = QGuiApplication.clipboard().text().strip()
        if is_url(clip) and "\n" not in clip:
            self.edit.setText(clip)
            self.edit.selectAll()
        layout.addWidget(self.edit)
        row = QHBoxLayout()
        row.addStretch(1)
        for label, append in (("Open", False), ("Add to Playlist", True)):
            button = QPushButton(label)
            button.clicked.connect(lambda _=False, append=append: self._accept(append))
            if not append:
                button.setDefault(True)
            row.addWidget(button)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        row.addWidget(cancel)
        layout.addLayout(row)
        self.setMinimumWidth(480)

    def _accept(self, append: bool):
        text = self.edit.text().strip()
        if not text:
            return
        self.url = text
        self.append = append
        self.accept()


def _slider(lo: int, hi: int, orientation=Qt.Horizontal) -> QSlider:
    slider = QSlider(orientation)
    slider.setRange(lo, hi)
    slider.setFocusPolicy(Qt.NoFocus)
    return slider


class ControlPanel(QDialog):
    """Non-modal panel with live audio/video/subtitle/playback controls (F7)."""

    def __init__(self, player):
        super().__init__(player)
        self.p = player
        self.setWindowTitle("Control Panel")
        self._loading = False
        self.tabs = QTabWidget()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.addWidget(self.tabs)
        self.tabs.addTab(self._audio_tab(), "Audio")
        self.tabs.addTab(self._video_tab(), "Video")
        self.tabs.addTab(self._subtitle_tab(), "Subtitles")
        self.tabs.addTab(self._playback_tab(), "Playback")
        self._timer = QTimer(self)
        self._timer.setInterval(400)
        self._timer.timeout.connect(self.refresh)
        self.setFixedSize(470, 330)

    def select_tab(self, name: str):
        for i in range(self.tabs.count()):
            if self.tabs.tabText(i) == name:
                self.tabs.setCurrentIndex(i)

    def showEvent(self, event):
        self.refresh()
        self._timer.start()

    def hideEvent(self, event):
        self._timer.stop()

    # -- tabs ------------------------------------------------------------------------------------
    def _audio_tab(self) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        top = QHBoxLayout()
        self.eq_enable = QCheckBox("Enable equalizer")
        self.eq_enable.toggled.connect(self._eq_changed)
        self.eq_preset = QComboBox()
        self.eq_preset.addItems(["Preset..."] + list(EQ_PRESETS))
        self.eq_preset.activated.connect(self._eq_preset)
        top.addWidget(self.eq_enable)
        top.addStretch(1)
        top.addWidget(self.eq_preset)
        outer.addLayout(top)
        grid = QGridLayout()
        self.eq_sliders = []
        for i, freq in enumerate(EQ_FREQS):
            slider = _slider(-12, 12, Qt.Vertical)
            slider.setMinimumHeight(130)
            slider.valueChanged.connect(self._eq_changed)
            label = QLabel(("%dk" % (freq // 1000)) if freq >= 1000 else str(freq))
            label.setAlignment(Qt.AlignCenter)
            label.setStyleSheet("color: #9a9a9a; font-size: 11px;")
            grid.addWidget(slider, 0, i, Qt.AlignHCenter)
            grid.addWidget(label, 1, i)
            self.eq_sliders.append(slider)
        outer.addLayout(grid)
        bottom = QHBoxLayout()
        self.normalize = QCheckBox("Normalize volume")
        self.normalize.toggled.connect(lambda on: None if self._loading else self.p.set_normalize(on))
        bottom.addWidget(self.normalize)
        bottom.addStretch(1)
        bottom.addWidget(QLabel("Audio sync (sec):"))
        self.audio_delay = QDoubleSpinBox()
        self.audio_delay.setRange(-60, 60)
        self.audio_delay.setSingleStep(0.05)
        self.audio_delay.setDecimals(2)
        self.audio_delay.valueChanged.connect(lambda v: self._set("audio-delay", v))
        bottom.addWidget(self.audio_delay)
        outer.addLayout(bottom)
        return page

    def _video_tab(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        self.image_sliders = {}
        for label, prop in (
            ("Brightness", "brightness"),
            ("Contrast", "contrast"),
            ("Saturation", "saturation"),
            ("Hue", "hue"),
            ("Gamma", "gamma"),
        ):
            slider = _slider(-100, 100)
            value = QLabel("0")
            value.setFixedWidth(34)
            value.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            slider.valueChanged.connect(lambda v, prop=prop, value=value: self._image(prop, v, value))
            row = QHBoxLayout()
            row.addWidget(slider)
            row.addWidget(value)
            form.addRow(label, row)
            self.image_sliders[prop] = (slider, value)
        reset = QPushButton("Reset")
        reset.clicked.connect(self.p.image_reset)
        form.addRow("", reset)
        return page

    def _subtitle_tab(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        self.sub_delay = QDoubleSpinBox()
        self.sub_delay.setRange(-600, 600)
        self.sub_delay.setSingleStep(0.5)
        self.sub_delay.setDecimals(1)
        self.sub_delay.valueChanged.connect(lambda v: self._set("sub-delay", v))
        form.addRow("Subtitle sync (sec)", self.sub_delay)
        self.sub_scale = _slider(30, 300)
        self.sub_scale.valueChanged.connect(lambda v: self._set("sub-scale", v / 100.0))
        form.addRow("Size", self.sub_scale)
        self.sub_pos = _slider(0, 150)
        self.sub_pos.valueChanged.connect(lambda v: self._set("sub-pos", v))
        form.addRow("Vertical position", self.sub_pos)
        self.sub_visible = QCheckBox("Show subtitles")
        self.sub_visible.toggled.connect(lambda on: self._set("sub-visibility", on))
        form.addRow("", self.sub_visible)
        reset = QPushButton("Reset")
        reset.clicked.connect(self.p.sub_reset)
        form.addRow("", reset)
        return page

    def _playback_tab(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        self.speed = _slider(20, 400)
        self.speed_label = QLabel("1.0x")
        self.speed_label.setFixedWidth(40)
        self.speed.valueChanged.connect(self._speed)
        row = QHBoxLayout()
        row.addWidget(self.speed)
        row.addWidget(self.speed_label)
        form.addRow("Speed", row)
        normal = QPushButton("Normal Speed")
        normal.clicked.connect(lambda: self.p.set_speed(1.0))
        form.addRow("", normal)
        row = QHBoxLayout()
        for label, fn in (
            ("Set A", lambda: self.p.ab_set("a")),
            ("Set B", lambda: self.p.ab_set("b")),
            ("Clear", self.p.ab_clear),
        ):
            button = QPushButton(label)
            button.clicked.connect(lambda _=False, fn=fn: fn())
            row.addWidget(button)
        form.addRow("A-B repeat", row)
        self.ab_label = QLabel("")
        form.addRow("", self.ab_label)
        return page

    # -- behaviour -------------------------------------------------------------------------------
    def _set(self, prop: str, value):
        if not self._loading:
            self.p.engine.set(prop, value)

    def _image(self, prop: str, value: int, label: QLabel):
        label.setText(str(value))
        self._set(prop, value)

    def _speed(self, value: int):
        self.speed_label.setText("%.2gx" % (value / 100.0) if value % 10 else "%.1fx" % (value / 100.0))
        self._set("speed", value / 100.0)

    def _eq_changed(self, *_):
        if self._loading:
            return
        self.p.settings["eq"] = [s.value() for s in self.eq_sliders]
        self.p.settings["eq_enabled"] = self.eq_enable.isChecked()
        self.p.apply_eq()

    def _eq_preset(self, index: int):
        name = self.eq_preset.itemText(index)
        if name not in EQ_PRESETS:
            return
        self._loading = True
        for slider, value in zip(self.eq_sliders, EQ_PRESETS[name], strict=False):
            slider.setValue(value)
        self.eq_enable.setChecked(True)
        self._loading = False
        self._eq_changed()
        self.eq_preset.setCurrentIndex(0)

    def refresh(self):
        engine = self.p.engine
        self._loading = True
        try:
            for slider, value in zip(self.eq_sliders, self.p.settings["eq"], strict=False):
                if not slider.isSliderDown():
                    slider.setValue(int(value))
            self.eq_enable.setChecked(bool(self.p.settings["eq_enabled"]))
            self.normalize.setChecked(self.p.normalize)
            if not self.audio_delay.hasFocus():
                self.audio_delay.setValue(float(engine.get("audio-delay", 0) or 0))
            for prop, (slider, label) in self.image_sliders.items():
                if not slider.isSliderDown():
                    value = int(engine.get(prop, 0) or 0)
                    slider.setValue(value)
                    label.setText(str(value))
            if not self.sub_delay.hasFocus():
                self.sub_delay.setValue(float(engine.get("sub-delay", 0) or 0))
            if not self.sub_scale.isSliderDown():
                self.sub_scale.setValue(int(round(float(engine.get("sub-scale", 1) or 1) * 100)))
            if not self.sub_pos.isSliderDown():
                self.sub_pos.setValue(int(engine.get("sub-pos", 100) or 0))
            self.sub_visible.setChecked(bool(engine.get("sub-visibility", True)))
            if not self.speed.isSliderDown():
                speed = float(engine.get("speed", 1) or 1)
                self.speed.setValue(int(round(speed * 100)))
                self.speed_label.setText("%.2fx" % speed)
            a, b = self.p.state.get("ab-loop-a"), self.p.state.get("ab-loop-b")
            self.ab_label.setText(
                "A: %s    B: %s"
                % (
                    fmt_time(a) if isinstance(a, (int, float)) else "--:--:--",
                    fmt_time(b) if isinstance(b, (int, float)) else "--:--:--",
                )
            )
        finally:
            self._loading = False


class PreferencesDialog(QDialog):
    def __init__(self, player):
        super().__init__(player)
        self.p = player
        s = player.settings
        self.setWindowTitle("Preferences")
        self.tabs = QTabWidget()
        layout = QVBoxLayout(self)
        layout.addWidget(self.tabs)

        # General
        page = QWidget()
        form = QFormLayout(page)
        self.autofit = QCheckBox("Resize the window to the video when a file opens")
        self.autofit.setChecked(bool(s["autofit"]))
        form.addRow(self.autofit)
        self.autofit_pct = QSpinBox()
        self.autofit_pct.setRange(30, 100)
        self.autofit_pct.setSuffix(" %")
        self.autofit_pct.setValue(int(s["autofit_max_pct"]))
        form.addRow("Largest window size (of the screen)", self.autofit_pct)
        self.resume = QCheckBox("Remember the playback position of each file")
        self.resume.setChecked(bool(s["resume"]))
        form.addRow(self.resume)
        self.use_x11 = QCheckBox("Run through X11 (XWayland) - enables Always on Top (needs restart)")
        self.use_x11.setChecked(bool(s["use_x11"]))
        form.addRow(self.use_x11)
        self.shot_dir = QLineEdit(s["screenshot_dir"])
        self.shot_dir.setPlaceholderText("~/Pictures/Samovar Lite")
        browse = QPushButton("Browse...")
        browse.clicked.connect(self._browse_shots)
        row = QHBoxLayout()
        row.addWidget(self.shot_dir)
        row.addWidget(browse)
        form.addRow("Screenshot folder", row)
        self.tabs.addTab(page, "General")

        # Playback
        page = QWidget()
        form = QFormLayout(page)
        self.seeks = {}
        for key, label in (
            ("seek_small", "Left / Right"),
            ("seek_medium", "Ctrl + Left / Right"),
            ("seek_large", "Shift + Left / Right"),
            ("seek_huge", "Ctrl + Alt + Left / Right"),
        ):
            spin = QSpinBox()
            spin.setRange(1, 3600)
            spin.setSuffix(" sec")
            spin.setValue(int(s[key]))
            form.addRow("Seek step: " + label, spin)
            self.seeks[key] = spin
        self.volume_step = QSpinBox()
        self.volume_step.setRange(1, 20)
        self.volume_step.setSuffix(" %")
        self.volume_step.setValue(int(s["volume_step"]))
        form.addRow("Volume step", self.volume_step)
        self.hwdec = QCheckBox("Use hardware video decoding when available")
        self.hwdec.setChecked(bool(s["hwdec"]))
        form.addRow(self.hwdec)
        self.tabs.addTab(page, "Playback")

        # Subtitles
        page = QWidget()
        form = QFormLayout(page)
        self.sub_font = QFontComboBox()
        if s["sub_font"]:
            self.sub_font.setCurrentFont(QFont(s["sub_font"]))
        self.sub_font_default = QCheckBox("Use the default font")
        self.sub_font_default.setChecked(not s["sub_font"])
        self.sub_font.setEnabled(bool(s["sub_font"]))
        self.sub_font_default.toggled.connect(lambda on: self.sub_font.setEnabled(not on))
        form.addRow("Font", self.sub_font)
        form.addRow("", self.sub_font_default)
        self.sub_size = QSpinBox()
        self.sub_size.setRange(10, 150)
        self.sub_size.setValue(int(s["sub_size"]))
        form.addRow("Size", self.sub_size)
        self.sub_bold = QCheckBox("Bold")
        self.sub_bold.setChecked(bool(s["sub_bold"]))
        form.addRow("", self.sub_bold)
        self.sub_codepage = QComboBox()
        for label, codepage in ENCODINGS:
            self.sub_codepage.addItem(label, codepage)
        self.sub_codepage.setCurrentIndex(max(0, self.sub_codepage.findData(s["sub_codepage"])))
        form.addRow("Text encoding for non-Unicode files", self.sub_codepage)
        self.sub_auto = QComboBox()
        for label, mode in (
            ("Same name as the video", "exact"),
            ("Names containing the video name", "fuzzy"),
            ("Every subtitle in the folder", "all"),
            ("Do not load automatically", "no"),
        ):
            self.sub_auto.addItem(label, mode)
        self.sub_auto.setCurrentIndex(max(0, self.sub_auto.findData(s["sub_auto"])))
        form.addRow("Load subtitles automatically", self.sub_auto)
        self.sub_lang = QLineEdit(s["preferred_sub_lang"])
        self.sub_lang.setPlaceholderText("e.g. fa,per,en")
        form.addRow("Preferred subtitle languages", self.sub_lang)
        self.tabs.addTab(page, "Subtitles")

        # Audio
        page = QWidget()
        form = QFormLayout(page)
        self.audio_lang = QLineEdit(s["preferred_audio_lang"])
        self.audio_lang.setPlaceholderText("e.g. en,fa")
        form.addRow("Preferred audio languages", self.audio_lang)
        self.tabs.addTab(page, "Audio")

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel | QDialogButtonBox.Apply)
        buttons.accepted.connect(self._ok)
        buttons.rejected.connect(self.reject)
        buttons.button(QDialogButtonBox.Apply).clicked.connect(self.apply)
        layout.addWidget(buttons)
        self.setMinimumWidth(560)

    def select_tab(self, name: str):
        for i in range(self.tabs.count()):
            if self.tabs.tabText(i) == name:
                self.tabs.setCurrentIndex(i)

    def _browse_shots(self):
        folder = QFileDialog.getExistingDirectory(self, "Screenshot folder", self.shot_dir.text())
        if folder:
            self.shot_dir.setText(folder)

    def apply(self):
        s = self.p.settings
        s["autofit"] = self.autofit.isChecked()
        s["autofit_max_pct"] = self.autofit_pct.value()
        s["resume"] = self.resume.isChecked()
        s["use_x11"] = self.use_x11.isChecked()
        s["screenshot_dir"] = self.shot_dir.text().strip()
        for key, spin in self.seeks.items():
            s[key] = spin.value()
        s["volume_step"] = self.volume_step.value()
        s["sub_font"] = "" if self.sub_font_default.isChecked() else self.sub_font.currentFont().family()
        s["sub_size"] = self.sub_size.value()
        s["sub_bold"] = self.sub_bold.isChecked()
        s["sub_codepage"] = self.sub_codepage.currentData()
        s["sub_auto"] = self.sub_auto.currentData()
        s["preferred_sub_lang"] = self.sub_lang.text().strip()
        s["preferred_audio_lang"] = self.audio_lang.text().strip()
        hwdec_changed = bool(s["hwdec"]) != self.hwdec.isChecked()
        s["hwdec"] = self.hwdec.isChecked()
        self.p.apply_settings(hwdec_changed)
        s.save()

    def _ok(self):
        self.apply()
        self.accept()


class TextDialog(QDialog):
    def __init__(self, parent, title: str, text: str, mono: bool = True, size=(620, 460)):
        super().__init__(parent)
        self.setWindowTitle(title)
        layout = QVBoxLayout(self)
        self.view = QPlainTextEdit(text)
        self.view.setReadOnly(True)
        if mono:
            self.view.setFont(skin.mono_font(12))
        layout.addWidget(self.view)
        row = QHBoxLayout()
        copy = QPushButton("Copy All")
        copy.clicked.connect(lambda: QGuiApplication.clipboard().setText(self.view.toPlainText()))
        close = QPushButton("Close")
        close.setDefault(True)
        close.clicked.connect(self.accept)
        row.addWidget(copy)
        row.addStretch(1)
        row.addWidget(close)
        layout.addLayout(row)
        self.resize(*size)
