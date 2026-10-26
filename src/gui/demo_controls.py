# src/demo_controls.py
"""
Showcase / playground for the controls panel.   Run from project root:

    python -m src.demo_controls

Layout (3 columns):
  col 0: vertical group capped at 230 px (scrolls inside) + narrow "Presets" group
  col 1: "Source" (linked controls), "Display tweaks" (HORIZONTAL group),
         "Vertical sliders" (row of vertical sliders + linked mean value)
  col 2: "Output" (conditional controls), collapsed "Advanced", "Dynamic" (add/remove), "Window"
"""
import sys
from math import pi

from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout, QPlainTextEdit
from PyQt6.QtCore import Qt

from src.gui import ControlsPanel, THEMES


def fmt(v):
    return f"{v:.6g}" if isinstance(v, float) else repr(v)


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")                      # neutral base; our stylesheet does the rest

    # ------------------------------------------------------------------ window
    root = QWidget()
    root.setObjectName("demoRoot")
    root.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    root.setWindowTitle("Controls demo")
    root.resize(1300, 900)
    lay = QVBoxLayout(root)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(0)

    panel = ControlsPanel(theme="dark")
    log = QPlainTextEdit(readOnly=True)
    log.setFixedHeight(130)
    log.setMaximumBlockCount(300)
    log_wrap = QWidget()
    lw = QVBoxLayout(log_wrap)
    lw.setContentsMargins(12, 0, 12, 12)
    lw.addWidget(log)
    lay.addWidget(panel, 1)
    lay.addWidget(log_wrap)

    state = {"theme": "dark"}

    def style_root():
        t = THEMES[state["theme"]]
        root.setStyleSheet(f"""
            #demoRoot {{ background: {t['bg']}; }}
            QPlainTextEdit {{ background: {t['input_bg']}; color: {t['text_dim']};
                border: 1px solid {t['border']}; border-radius: 8px; padding: 6px;
                font-family: 'DejaVu Sans Mono', monospace; font-size: 12px; }}
        """)

    style_root()

    # ============================================================ COLUMN 0
    A, P = "Slit geometry", "Presets"
    panel.add_group(A, column=0, max_height=230)          # vertical, scrolls if taller than 230 px
    panel.add_label("Vertical group, capped at 230 px: scroll inside.", group=A)
    panel.add_slider("a", "Slit width a", 10e-6, 500e-6, 100e-6,
                     unit="µm", unit_scale=1e-6, decimals=1, group=A)
    panel.add_slider("d", "Slit spacing d", 50e-6, 2000e-6, 500e-6,
                     unit="µm", unit_scale=1e-6, decimals=1, group=A)
    panel.limit("a", hi=lambda v: v["d"], depends_on=["d"])        # a can never exceed d
    panel.add_slider("Nx", "Slits in x", 1, 25, 5, integer=True, group=A)
    panel.add_slider("Ny", "Slits in y", 1, 25, 5, integer=True, group=A)
    panel.add_slider("tilt", "Tilt", -30, 30, 0, unit="°", decimals=1, step=0.5, group=A)
    panel.add_slider("phase", "Phase", 0, 2 * pi, 0, unit="rad", decimals=2, group=A)
    panel.add_entry("offset", "Offset", 0.0, unit="mm", unit_scale=1e-3,
                    min=-5e-3, max=5e-3, group=A)

    panel.add_group(P, column=0, max_width=340)           # narrow group that never grows past 340 px
    panel.add_preset("hene", "He-Ne", {"wavelength": 632.8e-9}, group=P, row="lasers")
    panel.add_preset("green", "Green", {"wavelength": 532e-9}, group=P, row="lasers")
    panel.add_preset("violet", "Violet", {"wavelength": 405e-9}, group=P, row="lasers")
    panel.add_button("square", "Square grid (Ny = Nx)",
                     on_click=lambda p: p.set_values({"Ny": p["Nx"]}), group=P)

    # ============================================================ COLUMN 1
    S, D, V = "Source", "Display tweaks", "Vertical sliders"
    panel.add_group(S, column=1)
    panel.add_slider("wavelength", "Wavelength λ", 400e-9, 700e-9, 632.8e-9,
                     unit="nm", unit_scale=1e-9, decimals=1, group=S)
    panel.add_entry("freq", "Frequency", 3e8 / 632.8e-9, unit="THz", unit_scale=1e12,
                    decimals=2, group=S)
    panel.link("wavelength", lambda v: {"freq": 3e8 / v["wavelength"]})            # λ -> f
    panel.link("freq", lambda v: {"wavelength": 3e8 / v["freq"]}, run_now=False)   # f -> λ
    panel.add_slider("z", "Distance Z", 0.1, 10.0, 1.0, unit="m", decimals=2, log=True, group=S)

    panel.add_group(D, column=1, orientation="horizontal")   # two vertical stacks, side by side
    # left stack
    panel.add_toggle("log_scale", "Log", False, label_width=40, group=D, row="left")
    panel.add_toggle("grid", "Grid", True, label_width=40, group=D, row="left")
    panel.add_toggle("invert", "Invert", False, label_width=40, group=D, row="left")
    # right stack: compact sliders without entry boxes
    panel.add_slider("zoom", "Zoom", 1, 10, 1, show_entry=False, label_width=55, group=D, row="right")
    panel.add_slider("contrast", "Contrast", 0, 1, 0.5, show_entry=False, label_width=55,
                     group=D, row="right")
    panel.add_slider("gamma", "Gamma", 0.1, 3.0, 1.0, step=0.05, show_entry=False,
                     label_width=55, group=D, row="right")
    panel.enable_when("gamma", lambda v: not v["log_scale"], depends_on=["log_scale"])

    # ---- vertical sliders: ordinary vertical group, same row="bands" -> side by side
    panel.add_group(V, column=1)
    bands = [("band0", "Low"), ("band1", "Mid"), ("band2", "High")]
    for key, name in bands:
        panel.add_slider(key, name, 0.0, 1.0, 0.5, decimals=2,
                         orientation="vertical", slider_length=150, entry_width=56,
                         group=V, row="bands")
    panel.add_slider("gain", "Gain", -12, 12, 0, integer=True, unit="dB",    # integer vertical slider
                     orientation="vertical", slider_length=150, entry_width=56,
                     group=V, row="bands")
    panel.add_entry("mean", "Mean level", 0.5, decimals=3, entry_width=70, group=V)
    keys = [k for k, _ in bands]
    panel.link(keys, lambda v: {"mean": sum(v[k] for k in keys) / len(keys)})      # derived value
    panel.add_preset("flat", "Flat", {k: 0.5 for k in keys}, group=V, row="vbtns")
    panel.add_preset("bass", "Bass boost", {"band0": 0.9, "band1": 0.5, "band2": 0.2},
                     group=V, row="vbtns")
    panel.add_preset("treble", "Treble boost", {"band0": 0.2, "band1": 0.5, "band2": 0.9},
                     group=V, row="vbtns")

    # ============================================================ COLUMN 2
    O, ADV, DYN, W = "Output", "Advanced", "Dynamic", "Window"
    panel.add_group(O, column=2)
    panel.add_choice("aperture", "Aperture", ["Rectangular", "Gaussian", "Hann"], group=O)
    panel.add_slider("sigma", "Gauss σ", 0.1, 5.0, 1.0, decimals=2, group=O)
    panel.show_when("sigma", lambda v: v["aperture"] == "Gaussian", depends_on=["aperture"])
    panel.add_choice("cmap", "Colormap",
                     [("Viridis", "viridis"), ("Inferno", "inferno"), ("Gray", "gray")], group=O)
    panel.add_separator(group=O)
    panel.add_entry("name", "Run name", "run1", kind="str", entry_width=120, group=O)
    panel.add_entry("grid_n", "Grid points", 512, kind="int", min=64, max=4096,
                    validator=lambda n: n % 2 == 0, tooltip="even integers only", group=O)

    panel.add_group(ADV, column=2, collapsed=True)       # click the header to expand
    panel.add_entry("eps", "Epsilon", 1e-9, decimals=12, group=ADV)
    panel.add_toggle("normalize", "Normalise", True, group=ADV)

    def add_test(p):
        n = len([k for k in p.controls if k.startswith("test")])
        p.add_slider(f"test{n}", f"Test slider {n}", 0, 1, 0.5, decimals=2, group=DYN)

    def remove_test(p):
        ks = [k for k in p.controls if k.startswith("test")]
        if ks:
            p.remove(ks[-1])

    panel.add_group(DYN, column=2, max_height=160)
    panel.add_button("add", "+ Add slider", on_click=add_test, variant="primary", group=DYN, row="dyn")
    panel.add_button("rem", "– Remove last", on_click=remove_test, group=DYN, row="dyn")

    def toggle_theme(p):
        state["theme"] = "light" if state["theme"] == "dark" else "dark"
        p.set_theme(state["theme"])
        style_root()

    panel.add_group(W, column=2)
    panel.add_button("theme", "Toggle dark / light", on_click=toggle_theme, group=W)

    # ============================================================ live log
    panel.parameterChanged.connect(lambda k, v: log.appendPlainText(f"{k:<12} = {fmt(v)}"))
    panel.buttonClicked.connect(lambda k: log.appendPlainText(f"[button] {k}"))
    log.appendPlainText("Move or type in any control. Derived changes (λ <-> f, band mean) show up too.")

    root.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()