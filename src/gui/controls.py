# src/gui/controls.py
"""
Fully dynamic, custom-styled control panel.

    panel = ControlsPanel(theme="dark", width=480)
    panel.add_slider("a", "Slit width", 10e-6, 500e-6, 100e-6, unit="µm", unit_scale=1e-6)
    panel.add_entry("z", "Distance", 1.0, unit="m")
    panel.add_button("go", "Run", on_click=lambda p: print(p.get_all_values()))
    panel.limit("a", hi=lambda v: v["d"], depends_on=["d"])     # constraints
    panel.link("wavelength", lambda v: {"freq": 3e8 / v["wavelength"]})  # derived values

All values are stored/emitted in SI units; the UI shows them in display units
(unit_scale). Controls can be added/removed at any time.
"""
from __future__ import annotations

import inspect
import math
import traceback
from typing import Any, Callable

from PyQt6.QtCore import Qt, pyqtSignal, QRectF, QPointF, QTimer
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush, QLinearGradient
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSlider, QLineEdit, QPushButton,
    QComboBox, QAbstractButton, QFrame, QScrollArea, QSizePolicy,
)

# =============================================================================
# THEMES
# =============================================================================
THEMES = {
    "dark": dict(
        font="Inter, 'Segoe UI', 'Ubuntu', sans-serif", font_size=13,
        bg="#14161c", panel="#1c1f27", border="#2c303b",
        text="#e6e8ee", text_dim="#8b91a1",
        accent="#4cc9f0", accent2="#7b5cff", on_accent="#0b0d12",
        groove="#2a2e39", handle="#14161c", input_bg="#12141a", danger="#ff5c7a",
    ),
    "light": dict(
        font="Inter, 'Segoe UI', 'Ubuntu', sans-serif", font_size=13,
        bg="#f3f4f8", panel="#ffffff", border="#d9dce6",
        text="#1d2030", text_dim="#6b7185",
        accent="#2563eb", accent2="#7c3aed", on_accent="#ffffff",
        groove="#dfe2ec", handle="#ffffff", input_bg="#f7f8fb", danger="#e11d48",
    ),
}


def build_qss(t: dict) -> str:
    return f"""
    #controlsRoot, #controlsContent {{ background: {t['bg']}; }}
    QScrollArea {{ background: transparent; border: none; }}
    QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
    QScrollBar::handle:vertical {{ background: {t['groove']}; border-radius: 4px; min-height: 24px; }}
    QScrollBar::handle:vertical:hover {{ background: {t['text_dim']}; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
    QWidget {{ font-family: {t['font']}; font-size: {t['font_size']}px; }}

    QFrame#group {{ background: {t['panel']}; border: 1px solid {t['border']}; border-radius: 12px; }}
    QPushButton#groupHeader {{
        background: transparent; border: none; color: {t['accent']};
        font-weight: 600; text-align: left; padding: 9px 14px;
    }}
    QPushButton#groupHeader:hover {{ color: {t['text']}; }}
    QFrame#separator {{ background: {t['border']}; border: none; }}

    QLabel {{ color: {t['text']}; background: transparent; }}
    QLabel#dim {{ color: {t['text_dim']}; }}
    QLabel:disabled {{ color: {t['text_dim']}; }}

    QLineEdit {{
        background: {t['input_bg']}; color: {t['text']};
        border: 1px solid {t['border']}; border-radius: 7px; padding: 4px 8px;
        selection-background-color: {t['accent']}; selection-color: {t['on_accent']};
    }}
    QLineEdit:hover {{ border: 1px solid {t['text_dim']}; }}
    QLineEdit:focus {{ border: 1px solid {t['accent']}; }}
    QLineEdit[invalid="true"] {{ border: 1px solid {t['danger']}; }}
    QLineEdit:disabled {{ color: {t['text_dim']}; background: {t['panel']}; }}

    QPushButton[role="action"] {{
        background: transparent; color: {t['text']};
        border: 1px solid {t['border']}; border-radius: 8px; padding: 6px 14px;
    }}
    QPushButton[role="action"]:hover {{ border: 1px solid {t['accent']}; }}
    QPushButton[role="action"]:pressed {{ background: {t['groove']}; }}
    QPushButton[role="action"][variant="primary"] {{
        background: {t['accent']}; color: {t['on_accent']}; border: 1px solid {t['accent']}; font-weight: 600;
    }}
    QPushButton[role="action"][variant="primary"]:hover {{ background: {t['accent2']}; border-color: {t['accent2']}; }}
    QPushButton[role="action"]:disabled {{ color: {t['text_dim']}; border-color: {t['groove']}; }}

    QComboBox {{
        background: {t['input_bg']}; color: {t['text']};
        border: 1px solid {t['border']}; border-radius: 7px; padding: 4px 28px 4px 8px;
    }}
    QComboBox:hover {{ border: 1px solid {t['text_dim']}; }}
    QComboBox:focus, QComboBox:on {{ border: 1px solid {t['accent']}; }}
    QScrollArea > QWidget > QWidget {{ background: transparent; }}
    QComboBox::drop-down {{ border: none; width: 24px; }}
    QComboBox QAbstractItemView {{
        background: {t['panel']}; color: {t['text']}; border: 1px solid {t['border']};
        selection-background-color: {t['accent']}; selection-color: {t['on_accent']}; outline: 0;
    }}
    """


# =============================================================================
# SMALL HELPERS
# =============================================================================
def _call(fn: Callable, *args):
    """Call fn with as many of args as it accepts (so on_click can take 0 or 1 args)."""
    try:
        n = len(inspect.signature(fn).parameters)
    except (TypeError, ValueError):
        n = len(args)
    return fn(*args[:n])


def _set_invalid(w: QWidget, flag: bool):
    try:
        w.setProperty("invalid", flag)
        w.style().unpolish(w)
        w.style().polish(w)
    except RuntimeError:        # widget already deleted
        pass


def _flash_invalid(w: QWidget):
    _set_invalid(w, True)
    QTimer.singleShot(700, lambda: _set_invalid(w, False))


def _fmt_trim(x: float, decimals: int) -> str:
    if x != 0 and abs(x) < 10 ** (-decimals):
        return f"{x:.{decimals}e}"
    s = f"{x:.{decimals}f}"
    return s.rstrip("0").rstrip(".") if "." in s else s


def _row(widget: QWidget, text: str, show_label: bool, label_width: int | None):
    lay = QHBoxLayout(widget)
    lay.setContentsMargins(0, 3, 0, 3)
    lay.setSpacing(10)
    lab = None
    if show_label and text:
        lab = QLabel(text)
        if label_width:
            lab.setMinimumWidth(label_width)
        lay.addWidget(lab)
    return lay, lab


# =============================================================================
# CUSTOM-PAINTED WIDGETS
# =============================================================================
class FancySlider(QSlider):
    def __init__(self, theme: dict, thickness: int = 26, orientation: str = "horizontal"):
        self._vertical = orientation == "vertical"
        super().__init__(Qt.Orientation.Vertical if self._vertical else Qt.Orientation.Horizontal)
        self._t, self._r, self._hover = theme, 9, False
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        if self._vertical:
            self.setFixedWidth(thickness)
            self.setMinimumHeight(120)
            self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        else:
            self.setFixedHeight(thickness)
            self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_theme(self, theme):
        self._t = theme
        self.update()

    def _axis_range(self):
        n = self.height() if self._vertical else self.width()
        return self._r + 2, n - self._r - 2

    def _pos_from_event(self, e):
        a0, a1 = self._axis_range()
        span = max(1.0, a1 - a0)
        if self._vertical:
            f = 1.0 - (e.position().y() - a0) / span      # top = maximum
        else:
            f = (e.position().x() - a0) / span
        f = min(max(f, 0.0), 1.0)
        return self.minimum() + round(f * (self.maximum() - self.minimum()))

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and self.isEnabled():
            self.setSliderDown(True)
            self.setValue(self._pos_from_event(e))
            e.accept()

    def mouseMoveEvent(self, e):
        if self.isSliderDown():
            self.setValue(self._pos_from_event(e))
        e.accept()

    def mouseReleaseEvent(self, e):
        self.setSliderDown(False)
        e.accept()

    def enterEvent(self, e):
        self._hover = True
        self.update()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._hover = False
        self.update()
        super().leaveEvent(e)

    def paintEvent(self, _):
        t = self._t
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setOpacity(1.0 if self.isEnabled() else 0.4)
        a0, a1 = self._axis_range()
        span = max(1, self.maximum() - self.minimum())
        frac = (self.value() - self.minimum()) / span
        gh = 6
        p.setPen(Qt.PenStyle.NoPen)

        if self._vertical:
            cx = self.width() / 2
            hy = a1 - frac * (a1 - a0)                      # handle position
            groove = QRectF(cx - gh / 2, a0, gh, a1 - a0)
            fill = QRectF(cx - gh / 2, hy, gh, max(0.0, a1 - hy))
            grad = QLinearGradient(0, a1, 0, a0)
            center = QPointF(cx, hy)
        else:
            cy = self.height() / 2
            hx = a0 + frac * (a1 - a0)
            groove = QRectF(a0, cy - gh / 2, a1 - a0, gh)
            fill = QRectF(a0, cy - gh / 2, max(0.0, hx - a0), gh)
            grad = QLinearGradient(a0, 0, a1, 0)
            center = QPointF(hx, cy)

        p.setBrush(QColor(t["groove"]))
        p.drawRoundedRect(groove, gh / 2, gh / 2)
        grad.setColorAt(0, QColor(t["accent2"]))
        grad.setColorAt(1, QColor(t["accent"]))
        p.setBrush(QBrush(grad))
        p.drawRoundedRect(fill, gh / 2, gh / 2)

        if self.isEnabled() and (self._hover or self.isSliderDown()):
            glow = QColor(t["accent"])
            glow.setAlpha(60)
            p.setBrush(glow)
            p.drawEllipse(center, self._r + 3, self._r + 3)
        p.setBrush(QColor(t["handle"]))
        p.setPen(QPen(QColor(t["accent"]), 2.2))
        p.drawEllipse(center, self._r - 2, self._r - 2)


class FancyToggle(QAbstractButton):
    def __init__(self, theme: dict):
        super().__init__()
        self._t = theme
        self.setCheckable(True)
        self.setFixedSize(44, 24)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_theme(self, theme):
        self._t = theme
        self.update()

    def paintEvent(self, _):
        t, w, h = self._t, self.width(), self.height()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setOpacity(1.0 if self.isEnabled() else 0.4)
        on = self.isChecked()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(t["accent"] if on else t["groove"]))
        p.drawRoundedRect(QRectF(0, 0, w, h), h / 2, h / 2)
        p.setBrush(QColor(t["on_accent"] if on else t["text_dim"]))
        cx = w - h / 2 if on else h / 2
        p.drawEllipse(QPointF(cx, h / 2), h / 2 - 4, h / 2 - 4)


class FancyCombo(QComboBox):
    def __init__(self, theme: dict):
        super().__init__()
        self._t = theme

    def set_theme(self, theme):
        self._t = theme
        self.update()

    def paintEvent(self, e):
        super().paintEvent(e)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor(self._t["text_dim"]), 1.8)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        cx, cy = self.width() - 14, self.height() / 2
        p.drawLine(QPointF(cx - 4, cy - 2), QPointF(cx, cy + 2))
        p.drawLine(QPointF(cx, cy + 2), QPointF(cx + 4, cy - 2))


# =============================================================================
# CONTROL BASE CLASS
# =============================================================================
class Control(QWidget):
    """Base for everything you can put in the panel."""
    changed = pyqtSignal(object)   # new value (value-bearing controls only)
    has_value = True

    def __init__(self, key: str, tooltip: str = ""):
        super().__init__()
        self.key = key
        self.default = None
        if tooltip:
            self.setToolTip(tooltip)

    def value(self):
        raise NotImplementedError

    def set_value(self, v, emit: bool = True):
        raise NotImplementedError

    def reset(self, emit: bool = True):
        self.set_value(self.default, emit)

    def set_theme(self, theme: dict):
        pass


# =============================================================================
# SLIDER (+ optional entry box)
# =============================================================================
class SliderControl(Control):
    def __init__(self, key, label, min, max, default=None, *,
                 unit="", unit_scale=1.0, decimals=3,
                 step=None, integer=False, log=False, steps=1000, clamp=True,
                 show_entry=True, show_label=True,
                 label_width=110, entry_width=90, slider_height=26, orientation="horizontal", slider_length=None,
                 tooltip="", theme=None):
        super().__init__(key, tooltip)
        if max <= min:
            raise ValueError(f"{key}: max must be > min")
        if log and min <= 0:
            raise ValueError(f"{key}: log slider needs min > 0")
        self.lo, self.hi = float(min), float(max)
        self.unit_scale = unit_scale
        self.integer, self.log, self.clamp = integer, log, clamp
        self.decimals = 0 if integer else decimals
        self.step = None if log else (float(step) if step else (1.0 if integer else None))
        self._steps_cfg = steps
        self._steps = self._compute_steps()

        d = self.lo if default is None else default
        self.default = self._cast(self._clip(d))
        self._value = self.default

        self.vertical = orientation == "vertical"
        theme = theme or THEMES["dark"]

        self.slider = FancySlider(theme, slider_height, orientation)
        self.slider.setRange(0, self._steps)
        self.slider.valueChanged.connect(self._on_slider)
        if slider_length:                                   # fixed length along the slider axis
            if self.vertical:
                self.slider.setFixedHeight(slider_length)
            else:
                self.slider.setFixedWidth(slider_length)

        self.entry = self.unit_label = self.label = None
        if show_entry:
            self.entry = QLineEdit()
            self.entry.setFixedWidth(entry_width)
            self.entry.setAlignment(Qt.AlignmentFlag.AlignCenter if self.vertical
                                    else Qt.AlignmentFlag.AlignRight)
            self.entry.editingFinished.connect(self._on_entry)
            if unit:
                self.unit_label = QLabel(unit)
                self.unit_label.setObjectName("dim")
                if not self.vertical:
                    self.unit_label.setMinimumWidth(26)

        if self.vertical:
            # label on top, slider in the middle, entry + unit underneath
            ctr = Qt.AlignmentFlag.AlignHCenter
            lay = QVBoxLayout(self)
            lay.setContentsMargins(4, 3, 4, 3)
            lay.setSpacing(6)
            if show_label and label:
                self.label = QLabel(label)
                lay.addWidget(self.label, 0, ctr)
            lay.addWidget(self.slider, 1, ctr)
            if self.entry:
                lay.addWidget(self.entry, 0, ctr)
            if self.unit_label:
                lay.addWidget(self.unit_label, 0, ctr)
        else:
            lay, self.label = _row(self, label, show_label, label_width)
            lay.addWidget(self.slider, 1)
            if self.entry:
                lay.addWidget(self.entry)
            if self.unit_label:
                lay.addWidget(self.unit_label)
        self._sync(False)

    # ----- mapping -----
    def _compute_steps(self):
        if self.step:
            return max(1, math.ceil((self.hi - self.lo) / self.step - 1e-9))
        return self._steps_cfg

    def _clip(self, v):
        return min(max(v, self.lo), self.hi)

    def _cast(self, v):
        return int(round(v)) if self.integer else float(v)

    def _pos_to_value(self, pos):
        if self.hi <= self.lo:
            return self.lo
        if self.step:
            return min(self.lo + pos * self.step, self.hi)
        f = pos / self._steps
        return self.lo * (self.hi / self.lo) ** f if self.log else self.lo + f * (self.hi - self.lo)

    def _value_to_pos(self, v):
        if self.hi <= self.lo:
            return 0
        v = self._clip(v)
        if self.step:
            return int(round((v - self.lo) / self.step))
        if self.log:
            f = math.log(v / self.lo) / math.log(self.hi / self.lo)
        else:
            f = (v - self.lo) / (self.hi - self.lo)
        return int(round(f * self._steps))

    def _fmt(self, v):
        return f"{v / self.unit_scale:.{self.decimals}f}"

    def _sync(self, from_slider):
        if not from_slider:
            self.slider.blockSignals(True)
            self.slider.setValue(self._value_to_pos(self._value))
            self.slider.blockSignals(False)
        if self.entry is not None:
            self.entry.setText(self._fmt(self._value))

    # ----- slots -----
    def _on_slider(self, pos):
        self._value = self._cast(self._pos_to_value(pos))
        self._sync(True)
        self.changed.emit(self._value)

    def _on_entry(self):
        try:
            x = float(self.entry.text().strip())
            if not math.isfinite(x):
                raise ValueError
            v = x * self.unit_scale
            if self.integer:
                v = round(v)
            if self.clamp:
                v = self._clip(v)
            v = self._cast(v)
        except ValueError:
            _flash_invalid(self.entry)
            self._sync(False)
            return
        changed = v != self._value
        self._value = v
        self._sync(False)
        if changed:
            self.changed.emit(self._value)

    # ----- public -----
    def value(self):
        return self._value

    def set_value(self, v, emit=True):
        v = float(v)
        if self.integer:
            v = round(v)
        if self.clamp:
            v = self._clip(v)
        self._value = self._cast(v)
        self._sync(False)
        if emit:
            self.changed.emit(self._value)

    def set_range(self, lo=None, hi=None, emit=True) -> bool:
        """Change the allowed range at runtime. Returns True if the value had to change."""
        lo = self.lo if lo is None else float(lo)
        hi = self.hi if hi is None else float(hi)
        if hi < lo:
            hi = lo
        if self.log and lo <= 0:
            raise ValueError(f"{self.key}: log slider needs lo > 0")
        self.lo, self.hi = lo, hi
        self._steps = self._compute_steps()
        self.slider.blockSignals(True)
        self.slider.setRange(0, self._steps)
        self.slider.blockSignals(False)
        old = self._value
        if self.clamp:
            self._value = self._cast(self._clip(self._value))
        self._sync(False)
        changed = self._value != old
        if changed and emit:
            self.changed.emit(self._value)
        return changed

    def set_theme(self, theme):
        self.slider.set_theme(theme)


# =============================================================================
# ENTRY (float / int / str)
# =============================================================================
class EntryControl(Control):
    def __init__(self, key, label, default=None, *, kind="float",
                 unit="", unit_scale=1.0, decimals=4, min=None, max=None,
                 validator=None, placeholder="", show_label=True,
                 label_width=110, entry_width=110, tooltip="", theme=None):
        super().__init__(key, tooltip)
        if kind not in ("float", "int", "str"):
            raise ValueError("kind must be 'float', 'int' or 'str'")
        self.kind, self.unit_scale, self.decimals = kind, unit_scale, decimals
        self.lo, self.hi, self.validator = min, max, validator
        if default is None:
            default = "" if kind == "str" else 0
        self.default = self._clip(self._coerce(default))
        self._value = self.default

        lay, self.label = _row(self, label, show_label, label_width)
        lay.addStretch(1)
        self.entry = QLineEdit()
        self.entry.setFixedWidth(entry_width)
        self.entry.setPlaceholderText(placeholder)
        if kind != "str":
            self.entry.setAlignment(Qt.AlignmentFlag.AlignRight)
        lay.addWidget(self.entry)
        if unit:
            self.unit_label = QLabel(unit)
            self.unit_label.setObjectName("dim")
            self.unit_label.setMinimumWidth(26)
            lay.addWidget(self.unit_label)
        self.entry.editingFinished.connect(self._on_entry)
        self._sync()

    def _coerce(self, v):
        if self.kind == "str":
            return str(v)
        return int(round(v)) if self.kind == "int" else float(v)

    def _clip(self, v):
        if self.kind == "str":
            return v
        if self.lo is not None and v < self.lo:
            v = self.lo
        if self.hi is not None and v > self.hi:
            v = self.hi
        return v

    def _fmt(self, v):
        if self.kind == "str":
            return v
        if self.kind == "int":
            return str(v)
        return _fmt_trim(v / self.unit_scale, self.decimals)

    def _sync(self):
        self.entry.setText(self._fmt(self._value))

    def _on_entry(self):
        try:
            t = self.entry.text().strip()
            if self.kind == "str":
                v = t
            else:
                x = float(t)
                if not math.isfinite(x):
                    raise ValueError
                v = self._coerce(x * self.unit_scale)
            v = self._clip(v)
            if self.validator is not None and not self.validator(v):
                raise ValueError
        except ValueError:
            _flash_invalid(self.entry)
            self._sync()
            return
        changed = v != self._value
        self._value = v
        self._sync()
        if changed:
            self.changed.emit(self._value)

    def value(self):
        return self._value

    def set_value(self, v, emit=True):
        self._value = self._clip(self._coerce(v))
        self._sync()
        if emit:
            self.changed.emit(self._value)

    def set_range(self, lo=None, hi=None, emit=True) -> bool:
        if lo is not None:
            self.lo = lo
        if hi is not None:
            self.hi = hi
        old = self._value
        self._value = self._clip(self._value)
        self._sync()
        changed = self._value != old
        if changed and emit:
            self.changed.emit(self._value)
        return changed


# =============================================================================
# CHOICE (dropdown)
# =============================================================================
class ChoiceControl(Control):
    def __init__(self, key, label, options, default=None, *, show_label=True,
                 label_width=110, tooltip="", theme=None):
        super().__init__(key, tooltip)
        lay, self.label = _row(self, label, show_label, label_width)
        self.combo = FancyCombo(theme or THEMES["dark"])
        self.combo.setCursor(Qt.CursorShape.PointingHandCursor)
        lay.addWidget(self.combo, 1)
        self._values: list = []
        self.set_options(options, default, emit=False)
        self.default = self.value()
        self.combo.currentIndexChanged.connect(lambda _i: self.changed.emit(self.value()))

    def _index_of(self, v):
        for i, val in enumerate(self._values):
            if val == v:
                return i
        for i in range(self.combo.count()):
            if self.combo.itemText(i) == str(v):
                return i
        return -1

    def set_options(self, options, default=None, emit=True):
        """options: ["A","B"]  or  [("Shown text", value), ...]"""
        self.combo.blockSignals(True)
        self.combo.clear()
        self._values = []
        for o in options:
            text, val = (o[0], o[1]) if isinstance(o, (tuple, list)) else (str(o), o)
            self.combo.addItem(text)
            self._values.append(val)
        idx = self._index_of(default) if default is not None else 0
        self.combo.setCurrentIndex(max(idx, 0))
        self.combo.blockSignals(False)
        if emit:
            self.changed.emit(self.value())

    def value(self):
        i = self.combo.currentIndex()
        return self._values[i] if 0 <= i < len(self._values) else None

    def set_value(self, v, emit=True):
        i = self._index_of(v)
        if i < 0:
            raise ValueError(f"{self.key}: '{v}' is not one of the options")
        self.combo.blockSignals(True)
        self.combo.setCurrentIndex(i)
        self.combo.blockSignals(False)
        if emit:
            self.changed.emit(self.value())

    def set_theme(self, theme):
        self.combo.set_theme(theme)


# =============================================================================
# TOGGLE (on/off switch)
# =============================================================================
class ToggleControl(Control):
    def __init__(self, key, label, default=False, *, show_label=True,
                 label_width=110, tooltip="", theme=None):
        super().__init__(key, tooltip)
        lay, self.label = _row(self, label, show_label, label_width)
        lay.addStretch(1)
        self.toggle = FancyToggle(theme or THEMES["dark"])
        self.toggle.setChecked(bool(default))
        lay.addWidget(self.toggle)
        self.default = bool(default)
        self.toggle.toggled.connect(lambda c: self.changed.emit(bool(c)))

    def value(self):
        return self.toggle.isChecked()

    def set_value(self, v, emit=True):
        self.toggle.blockSignals(True)
        self.toggle.setChecked(bool(v))
        self.toggle.blockSignals(False)
        self.toggle.update()
        if emit:
            self.changed.emit(self.value())

    def set_theme(self, theme):
        self.toggle.set_theme(theme)


# =============================================================================
# BUTTON, LABEL, SEPARATOR  (no value)
# =============================================================================
class ButtonControl(Control):
    has_value = False
    activated = pyqtSignal()

    def __init__(self, key, text, *, variant="default", tooltip="", theme=None):
        super().__init__(key, tooltip)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 3, 0, 3)
        self.button = QPushButton(text)
        self.button.setProperty("role", "action")
        self.button.setProperty("variant", variant)
        self.button.setCursor(Qt.CursorShape.PointingHandCursor)
        lay.addWidget(self.button)
        self.button.clicked.connect(lambda _=False: self.activated.emit())

    def value(self):
        return None

    def set_value(self, v, emit=True):
        pass

    def reset(self, emit=True):
        pass

    def set_text(self, text):
        self.button.setText(text)


class LabelControl(Control):
    has_value = False

    def __init__(self, key, text, *, dim=True, tooltip=""):
        super().__init__(key, tooltip)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 2, 0, 2)
        self.label = QLabel(text)
        self.label.setWordWrap(True)
        if dim:
            self.label.setObjectName("dim")
        lay.addWidget(self.label)

    def value(self):
        return None

    def set_value(self, v, emit=True):
        pass

    def reset(self, emit=True):
        pass

    def set_text(self, text):
        self.label.setText(text)


class SeparatorControl(Control):
    has_value = False

    def __init__(self, key):
        super().__init__(key)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 6, 0, 6)
        line = QFrame()
        line.setObjectName("separator")
        line.setFixedHeight(1)
        lay.addWidget(line)

    def value(self):
        return None

    def set_value(self, v, emit=True):
        pass

    def reset(self, emit=True):
        pass


# =============================================================================
# GROUP (collapsible card that holds controls / rows of controls)
# =============================================================================
class Group(QFrame):
    """
    orientation="vertical"   : controls stack top-to-bottom; row="x" puts controls side by side.
    orientation="horizontal" : each row="x" name becomes a vertical stack, stacks sit side by side.
    max_height               : pixel cap on the body; content scrolls inside instead of growing.
    """
    def __init__(self, name, collapsed=False, collapsible=True,
                 orientation="vertical", max_height=None):
        super().__init__()
        self.setObjectName("group")
        self.name, self.collapsible, self.orientation = name, collapsible, orientation
        horiz = orientation == "horizontal"

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.header = QPushButton()
        self.header.setObjectName("groupHeader")
        self.header.setCursor(Qt.CursorShape.PointingHandCursor if collapsible
                              else Qt.CursorShape.ArrowCursor)
        self.header.clicked.connect(lambda _=False: self.toggle())

        self.body = QWidget()
        self.body_layout = QHBoxLayout(self.body) if horiz else QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(12, 0, 12, 10)
        self.body_layout.setSpacing(12 if horiz else 2)
        outer.addWidget(self.header)

        self.scroll = None
        self._holder = self.body
        if max_height:
            self.scroll = QScrollArea()
            self.scroll.setWidgetResizable(True)
            self.scroll.setFrameShape(QFrame.Shape.NoFrame)
            self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            self.scroll.viewport().setAutoFillBackground(False)
            self.scroll.setMaximumHeight(max_height)
            self.scroll.setWidget(self.body)
            self._holder = self.scroll
        outer.addWidget(self._holder)

        self._rows: dict[str, object] = {}
        self.set_collapsed(collapsed)

    def set_collapsed(self, c: bool):
        self._collapsed = bool(c)
        self._holder.setVisible(not self._collapsed)
        arrow = "▸" if self._collapsed else "▾"
        self.header.setText(f"{arrow}  {self.name}" if self.collapsible else self.name)

    def toggle(self):
        if self.collapsible:
            self.set_collapsed(not self._collapsed)

    def add(self, widget: QWidget, row: str | None = None):
        horiz = self.orientation == "horizontal"
        if row is None and not horiz:
            self.body_layout.addWidget(widget)
            return
        if row is None:                       # horizontal group: lone control = its own stack
            row = f"_stack{len(self._rows)}"
        lay = self._rows.get(row)
        if lay is None:
            holder = QWidget()
            lay = QVBoxLayout(holder) if horiz else QHBoxLayout(holder)
            lay.setContentsMargins(0, 0, 0, 0)
            lay.setSpacing(2 if horiz else 8)
            self._rows[row] = lay
            if horiz:
                self.body_layout.addWidget(holder, 1, Qt.AlignmentFlag.AlignTop)
            else:
                self.body_layout.addWidget(holder)
        lay.addWidget(widget)

    def remove(self, widget: QWidget):
        for name, lay in list(self._rows.items()):
            if lay.indexOf(widget) >= 0:
                lay.removeWidget(widget)
                if lay.count() == 0:
                    holder = lay.parentWidget()
                    self._rows.pop(name)
                    self.body_layout.removeWidget(holder)
                    holder.setParent(None)
                    holder.deleteLater()
                break
        else:
            self.body_layout.removeWidget(widget)
        widget.setParent(None)
        widget.deleteLater()


# =============================================================================
# THE PANEL
# =============================================================================
class _Link:
    __slots__ = ("sources", "fn")

    def __init__(self, sources, fn):
        self.sources, self.fn = sources, fn


class ControlsPanel(QWidget):
    parametersChanged = pyqtSignal(dict)       # all values
    parameterChanged = pyqtSignal(str, object) # (key, value) - also fires for derived keys
    buttonClicked = pyqtSignal(str)            # button key

    def __init__(self, theme="dark", *, label_width=110, entry_width=90,
                 default_group="Parameters", show_reset=True, width=None,
                 margins=12, spacing=10):
        super().__init__()
        self.setObjectName("controlsRoot")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.label_width, self.entry_width = label_width, entry_width
        self.default_group = default_group
        self._theme = THEMES[theme] if isinstance(theme, str) else theme
        self.controls: dict[str, Control] = {}
        self.groups: dict[str, Group] = {}
        self._group_of: dict[str, str] = {}
        self._links: list[_Link] = []
        self._auto = 0

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.content = QWidget()
        self.content.setObjectName("controlsContent")
        self.content.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._spacing = spacing
        self._hbox = QHBoxLayout(self.content)          # holds the columns
        self._hbox.setContentsMargins(margins, margins, margins, margins)
        self._hbox.setSpacing(spacing)
        self._columns: list[QVBoxLayout] = []
        self._group_col: dict[str, int] = {}
        self._ensure_column(0)
        self.scroll.setWidget(self.content)
        outer.addWidget(self.scroll, 1)

        self.reset_btn = None
        if show_reset:
            footer = QWidget()
            fl = QHBoxLayout(footer)
            fl.setContentsMargins(margins, 4, margins, margins)
            self.reset_btn = QPushButton("Reset to defaults")
            self.reset_btn.setProperty("role", "action")
            self.reset_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            self.reset_btn.clicked.connect(lambda _=False: self.reset())
            fl.addWidget(self.reset_btn)
            outer.addWidget(footer)

        if width:
            self.setFixedWidth(width)
        self.set_theme(self._theme)

    # ------------------------------------------------------------ adding stuff
    def _next_key(self, prefix):
        self._auto += 1
        return f"_{prefix}{self._auto}"

    def _register(self, ctrl: Control, group, row, width, height):
        if ctrl.key in self.controls:
            raise KeyError(f"duplicate control key '{ctrl.key}'")
        if width:
            ctrl.setFixedWidth(width)
        if height:
            ctrl.setFixedHeight(height)
        g = self.add_group(group or self.default_group)
        g.add(ctrl, row)
        self.controls[ctrl.key] = ctrl
        self._group_of[ctrl.key] = g.name
        if ctrl.has_value:
            ctrl.changed.connect(lambda _v, k=ctrl.key: self._on_control_changed(k))
        return ctrl

    def add_slider(self, key, label, min, max, default=None, *,
                   group=None, row=None, width=None, height=None, **kw):
        kw.setdefault("label_width", self.label_width)
        kw.setdefault("entry_width", self.entry_width)
        c = SliderControl(key, label, min, max, default, theme=self._theme, **kw)
        return self._register(c, group, row, width, height)

    def add_entry(self, key, label, default=None, *,
                  group=None, row=None, width=None, height=None, **kw):
        kw.setdefault("label_width", self.label_width)
        kw.setdefault("entry_width", self.entry_width)
        c = EntryControl(key, label, default, theme=self._theme, **kw)
        return self._register(c, group, row, width, height)

    def add_choice(self, key, label, options, default=None, *,
                   group=None, row=None, width=None, height=None, **kw):
        kw.setdefault("label_width", self.label_width)
        c = ChoiceControl(key, label, options, default, theme=self._theme, **kw)
        return self._register(c, group, row, width, height)

    def add_toggle(self, key, label, default=False, *,
                   group=None, row=None, width=None, height=None, **kw):
        kw.setdefault("label_width", self.label_width)
        c = ToggleControl(key, label, default, theme=self._theme, **kw)
        return self._register(c, group, row, width, height)

    def add_button(self, key, text, on_click=None, *, variant="default",
                   group=None, row=None, width=None, height=None, tooltip=""):
        """on_click may take 0 args, or 1 arg (the panel)."""
        c = ButtonControl(key, text, variant=variant, tooltip=tooltip, theme=self._theme)
        c.activated.connect(lambda k=key, f=on_click: self._on_button(k, f))
        return self._register(c, group, row, width, height)

    def add_preset(self, key, text, values: dict, **kw):
        """Button that sets several controls at once."""
        return self.add_button(key, text, on_click=lambda p: p.set_values(values), **kw)

    def add_label(self, text, key=None, *, group=None, row=None, dim=True):
        c = LabelControl(key or self._next_key("label"), text, dim=dim)
        return self._register(c, group, row, None, None)

    def add_separator(self, key=None, *, group=None):
        c = SeparatorControl(key or self._next_key("sep"))
        return self._register(c, group, None, None, None)

    def build(self, specs: list[dict]):
        """Declarative: [{"type": "slider", "key": ..., ...}, {"type": "button", ...}]"""
        for s in specs:
            s = dict(s)
            getattr(self, "add_" + s.pop("type"))(**s)

    # ------------------------------------------------------------ removing stuff
    def _remove(self, key) -> bool:
        ctrl = self.controls.pop(key)
        self.groups[self._group_of.pop(key)].remove(ctrl)
        self._links = [l for l in self._links if l.sources is None or key not in l.sources]
        return ctrl.has_value

    def remove(self, key):
        if self._remove(key):
            self.parametersChanged.emit(self.get_all_values())

    def _ensure_column(self, i: int):
        while len(self._columns) <= i:
            w = QWidget()
            lay = QVBoxLayout(w)
            lay.setContentsMargins(0, 0, 0, 0)
            lay.setSpacing(self._spacing)
            lay.addStretch(1)                           # keeps groups packed at the top
            self._columns.append(lay)
            self._hbox.addWidget(w, 1)

    def add_group(self, name, *, column=0, collapsed=False, collapsible=True,
                  orientation="vertical", width=None, max_width=None, max_height=None) -> Group:
        if name in self.groups:
            return self.groups[name]
        g = Group(name, collapsed, collapsible, orientation, max_height)
        self._ensure_column(column)
        lay = self._columns[column]
        lay.insertWidget(lay.count() - 1, g)
        if width:
            g.setFixedWidth(width)
        if max_width:
            g.setMaximumWidth(max_width)
        if width or max_width:
            lay.setAlignment(g, Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.groups[name] = g
        self._group_col[name] = column
        return g

    def remove_group(self, name):
        had = False
        for k in [k for k, g in self._group_of.items() if g == name]:
            had |= self._remove(k)
        g = self.groups.pop(name)
        self._columns[self._group_col.pop(name)].removeWidget(g)
        g.setParent(None)
        g.deleteLater()
        if had:
            self.parametersChanged.emit(self.get_all_values())

    def clear(self):
        for name in list(self.groups):
            self.remove_group(name)

    # --------------------------------------------------------------- values
    def control(self, key) -> Control:
        return self.controls[key]

    def get_all_values(self) -> dict:
        return {k: c.value() for k, c in self.controls.items() if c.has_value}

    values = get_all_values

    def __getitem__(self, key):
        return self.controls[key].value()

    def __setitem__(self, key, value):
        self.set_values({key: value})

    def __contains__(self, key):
        return key in self.controls

    def set_values(self, values: dict, emit=True):
        for k, v in values.items():
            self.controls[k].set_value(v, emit=False)
        if emit:
            derived = self._propagate(set(values))
            self._emit(list(values) + derived)

    def reset(self, emit=True):
        self.set_values({k: c.default for k, c in self.controls.items() if c.has_value}, emit)

    # -------------------------------------------------------------- relations
    def link(self, sources, fn: Callable[[dict], dict | None], run_now=True) -> _Link:
        """
        When any of `sources` (key, list of keys, or None = any) changes, call
        fn(values_dict). If fn returns {key: new_value}, those controls are updated.
        Each link fires at most once per user action, and never overwrites the
        control the user just touched, so two-way links (λ <-> f) don't loop.
        """
        if isinstance(sources, str):
            sources = [sources]
        lk = _Link(None if sources is None else set(sources), fn)
        self._links.append(lk)
        if run_now:
            for k, v in self._run_link(lk).items():
                if k in self.controls:
                    self.controls[k].set_value(v, emit=False)
        return lk

    def unlink(self, lk: _Link):
        if lk in self._links:
            self._links.remove(lk)

    def limit(self, key, *, lo=None, hi=None, depends_on=None):
        """Dynamic range: lo/hi can be numbers or functions of the values dict."""
        ctrl = self.controls[key]

        def apply(values):
            l = lo(values) if callable(lo) else lo
            h = hi(values) if callable(hi) else hi
            return {key: ctrl.value()} if ctrl.set_range(l, h, emit=False) else None

        return self.link(depends_on, apply)

    def enable_when(self, keys, predicate: Callable[[dict], bool], depends_on=None):
        keys = [keys] if isinstance(keys, str) else keys

        def apply(values):
            ok = bool(predicate(values))
            for k in keys:
                self.controls[k].setEnabled(ok)

        return self.link(depends_on, apply)

    def show_when(self, keys, predicate: Callable[[dict], bool], depends_on=None):
        keys = [keys] if isinstance(keys, str) else keys

        def apply(values):
            ok = bool(predicate(values))
            for k in keys:
                self.controls[k].setVisible(ok)

        return self.link(depends_on, apply)

    # -------------------------------------------------------------- internals
    def _run_link(self, lk) -> dict:
        try:
            return lk.fn(self.get_all_values()) or {}
        except Exception:
            traceback.print_exc()    # don't let a bad link kill the GUI
            return {}

    def _propagate(self, changed: set) -> list:
        touched, derived, fired = set(changed), [], set()
        queue = list(changed)
        while queue:
            k = queue.pop(0)
            for lk in self._links:
                if id(lk) in fired or (lk.sources is not None and k not in lk.sources):
                    continue
                fired.add(id(lk))
                for uk, uv in self._run_link(lk).items():
                    if uk in touched or uk not in self.controls:
                        continue
                    self.controls[uk].set_value(uv, emit=False)
                    touched.add(uk)
                    derived.append(uk)
                    queue.append(uk)
        return derived

    def _emit(self, keys):
        for k in keys:
            if k in self.controls:
                self.parameterChanged.emit(k, self.controls[k].value())
        self.parametersChanged.emit(self.get_all_values())

    def _on_control_changed(self, key):
        self._emit([key] + self._propagate({key}))

    def _on_button(self, key, fn):
        self.buttonClicked.emit(key)
        if fn is not None:
            try:
                _call(fn, self)
            except Exception:
                traceback.print_exc()

    # ------------------------------------------------------------------ theme
    def set_theme(self, theme):
        self._theme = THEMES[theme] if isinstance(theme, str) else theme
        self.setStyleSheet(build_qss(self._theme))
        for c in self.controls.values():
            c.set_theme(self._theme)


# =============================================================================
# DEMO:  python -m src.gui.controls
# =============================================================================
if __name__ == "__main__":
    import sys
    from PyQt6.QtWidgets import QApplication

    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    panel = ControlsPanel(theme="dark", width=950)          # wider panel for two columns

    # Column 0: normal vertical group, body capped at 220 px and scrolls if longer
    panel.add_group("Slit geometry", column=0, max_height=220)
    panel.add_slider("a", "Slit width", 10e-6, 500e-6, 100e-6, unit="µm", unit_scale=1e-6, group="Slit geometry")
    panel.add_slider("d", "Slit spacing", 50e-6, 2000e-6, 500e-6, unit="µm", unit_scale=1e-6, group="Slit geometry")

    # Column 1: horizontal group made of two vertical stacks ("left" and "right")
    panel.add_group("Source", column=1, orientation="horizontal")
    panel.add_slider("wavelength", "λ", 400e-9, 700e-9, 632.8e-9, unit="nm", unit_scale=1e-9,
                    group="Source", row="left")
    panel.add_entry("freq", "Freq", 4.74e14, unit="THz", unit_scale=1e12,
                    group="Source", row="left")             # stacked under λ
    panel.add_slider("z", "Z", 0.1, 10, 1, log=True, group="Source", row="right")
    panel.add_toggle("log", "Log scale", False, group="Source", row="right")

    # A narrow group that never grows wider than 300 px
    panel.add_group("Presets", column=1, max_width=300)
    def add_test(panel):
        n = len([k for k in panel.controls if k.startswith("test")])
        panel.add_slider(f"test{n}", f"Test slider {n}", 0, 1, 0.5, decimals=2, group=G4)

    def remove_test(panel):
        ks = [k for k in panel.controls if k.startswith("test")]
        if ks:
            panel.remove(ks[-1])

    sys.exit(app.exec())