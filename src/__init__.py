"""CINT Stubble Burning Detection Package."""

import importlib

clean_detections = importlib.import_module("src.01_clean_detections")
hotspot_analysis = importlib.import_module("src.02_hotspot_analysis")
sentinel2_composites = importlib.import_module("src.03_sentinel2_composites")

__all__ = ["clean_detections", "hotspot_analysis", "sentinel2_composites"]
