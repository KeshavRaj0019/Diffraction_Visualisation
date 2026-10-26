# src/compute/diffraction.py

import numpy as np


class FarFieldCalculator:
    """
    Computes 2D Far-Field (Fraunhofer) Diffraction intensity profiles 
    for crossed-slit grid apertures.
    """
    def __init__(self, wavelength: float = 632.8e-9, slit_width: float = 100e-6, slit_spacing: float = 500e-6):
        """
        Parameters:
        -----------
        wavelength : float
            Wavelength of light (λ) in meters (default: 632.8 nm - HeNe Laser).
        slit_width : float
            Slit aperture width (a) in meters (default: 100 µm).
        slit_spacing : float
            Distance between adjacent slit centers (d) in meters (default: 500 µm).
        """
        self.wavelength = wavelength
        self.a = slit_width
        self.d = slit_spacing

    def compute_2d_intensity(self, grid_size: int = 400, screen_size: float = 0.04) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Calculates the normalized 2D intensity profile on a observation screen.

        Parameters:
        -----------
        grid_size : int
            Resolution of the sampling grid (N x N points).
        screen_size : float
            Width and height of the square viewing screen in meters.

        Returns:
        --------
        X, Y : np.ndarray
            2D meshgrid mesh coordinates of the screen (meters).
        intensity : np.ndarray
            Normalized 2D intensity pattern I(x, y).
        """
        # Create spatial grid on screen
        x = np.linspace(-screen_size / 2, screen_size / 2, grid_size)
        y = np.linspace(-screen_size / 2, screen_size / 2, grid_size)
        X, Y = np.meshgrid(x, y)

        # Single-Slit Diffraction Factors (Sinc function envelope)
        # alpha = (pi * a * sin(theta_x)) / lambda ~ (pi * a * X) / (lambda * Z)
        # Using np.sinc(u) which evaluates sin(pi * u) / (pi * u)
        u_x = (self.a * X) / (self.wavelength)
        u_y = (self.a * Y) / (self.wavelength)
        
        diffraction_x = np.sinc(u_x)
        diffraction_y = np.sinc(u_y)
        
        # Single-aperture envelope intensity
        envelope = (diffraction_x * diffraction_y) ** 2

        # Interference Factors for Crossed-Slit Grid
        gamma_x = (np.pi * self.d * X) / self.wavelength
        gamma_y = (np.pi * self.d * Y) / self.wavelength
        
        interference = (np.cos(gamma_x) * np.cos(gamma_y)) ** 2

        # Combined Intensity Distribution
        intensity = envelope * interference

        # Normalize peak intensity to 1.0
        max_val = np.max(intensity)
        if max_val > 0:
            intensity = intensity / max_val

        return X, Y, intensity