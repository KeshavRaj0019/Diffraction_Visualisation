# src/main.py

import sys
import numpy as np
from PyQt6.QtWidgets import QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
import matplotlib.pyplot as plt

# Internal module imports
from src.gui.controls import ControlsPanel
from src.compute.diffraction import DiffractionCalculator


class PlotCanvas(FigureCanvas):
    """
    Matplotlib canvas dedicated to displaying the 2D Far-Field Diffraction pattern.
    """
    def __init__(self, parent=None, width=5, height=5, dpi=100):
        self.fig, self.ax = plt.subplots(figsize=(width, height), dpi=dpi)
        super().__init__(self.fig)
        self.setParent(parent)

        # Initial placeholder image object
        self.im = None
        self.ax.set_title("2D Far-Field Diffraction Pattern", fontsize=11, pad=10)
        self.ax.set_xlabel("x (m)")
        self.ax.set_ylabel("y (m)")
        self.fig.tight_layout()

    def update_plot(self, X, Y, intensity):
        """
        Efficiently updates the 2D heatmap display when input parameters change.
        """
        self.ax.clear()
        self.ax.set_title("2D Far-Field Diffraction Pattern", fontsize=11, pad=10)
        self.ax.set_xlabel("x (m)")
        self.ax.set_ylabel("y (m)")

        # Render 2D intensity profile using an 'inferno' or 'viridis' colormap
        extent = [X.min(), X.max(), Y.min(), Y.max()]
        self.im = self.ax.imshow(
            intensity,
            cmap='inferno',
            extent=extent,
            origin='lower',
            aspect='equal'
        )
        self.draw()


class MainWindow(QMainWindow):
    """
    Main Application Window integrating controls and plot views.
    """
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PYL209 - 2D Far-Field Diffraction Simulator")
        self.resize(1000, 600)

        # Core logic calculation instance
        self.calculator = DiffractionCalculator()

        # Layout setup
        central_widget = QWidget()
        main_layout = QHBoxLayout(central_widget)

        # 1. Left Panel: Controls
        self.controls_panel = ControlsPanel()
        main_layout.addWidget(self.controls_panel, stretch=1)

        # 2. Right Panel: Plot Canvas
        self.plot_canvas = PlotCanvas(self)
        main_layout.addWidget(self.plot_canvas, stretch=2)

        self.setCentralWidget(central_widget)

        # Connect GUI parameter emissions to calculation controller
        self.controls_panel.parametersChanged.connect(self._on_parameters_changed)

        # Initial render on startup
        self._on_parameters_changed(self.controls_panel.get_all_values())

    def _on_parameters_changed(self, params: dict):
        """
        Callback executed whenever a slider or entry box value changes.
        """
        # Update calculator state
        self.calculator.a = params.get("a", 100e-6)
        self.calculator.d = params.get("d", 500e-6)
        self.calculator.wavelength = params.get("wavelength", 632.8e-9)

        # Perform 2D intensity calculation
        X, Y, intensity = self.calculator.compute_2d_intensity()

        # Render updated intensity matrix
        self.plot_canvas.update_plot(X, Y, intensity)


def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()