"""
Shared configuration for the Starlink obstruction analysis pipeline.

Set STARLINK_DATA_PATH to override the default data root.
"""

import os
from pathlib import Path

# Root directory containing all dataset files.
# Override via environment variable to avoid editing source files.
DATA_PATH: str = os.environ.get(
    "STARLINK_DATA_PATH",
    "/data/starlink/home_files/data/starlink",
)

# WGS-84 coordinates of the measurement site (Ithaca, NY).
DISH_LOCATION: tuple[float, float] = (42.44494792436863, -76.47977371349182)

TIMEZONE: str = "US/Eastern"

# Minimum satellite elevation (degrees) used when computing rise/set events.
MIN_ELEVATION_DEGREES: float = 25.0

# Center pixel of the Starlink obstruction map (123×123 grayscale image).
OBSMAP_CENTER_X: int = 62
OBSMAP_CENTER_Y: int = 62

# Pixels-to-degrees scale: distance of 1 px from center ≈ 1 / PIXEL_SCALE degrees from zenith.
PIXEL_SCALE: float = 1.3333

# Minimum pixel run length required before treating an obstruction-map trace
# as a valid satellite trajectory (filters stray pixels).
MIN_TRAJECTORY_PIXELS: int = 8

# Dish identifiers used throughout the dataset.
DISH_IDS: list[str] = ["pi1", "pi2"]
