"""Automated tests for CINT Stubble Burning Detection pipeline.

Tests data integrity, filtering logic, geometric operations,
hexagonal grid dimensions, and deliverable specifications.
"""

import sys
import math
from pathlib import Path
import pytest
import numpy as np
import pandas as pd
import geopandas as gpd
from shapely.geometry import Polygon, Point
from PIL import Image

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.config import (
    SUOMI_VIIRS_PATH,
    NOAA20_VIIRS_PATH,
    HARYANA_STATE_GEOJSON,
    HARYANA_DISTRICTS_GEOJSON,
    CLEANED_FIRES_GEOJSON,
    CLEANED_FIRES_CSV,
    HEXGRID_HOTSPOTS_GEOJSON,
    DISTRICT_SUMMARY_CSV,
    COMPOSITE_PREVIEW_PNG,
    RETAINED_CONFIDENCE,
    EXCLUDED_CONFIDENCE,
    CROPLAND_CLASS_VALUE,
    HEX_SPACING_METERS,
    S2_PRE_START,
    S2_PRE_END,
    S2_POST_START,
    S2_POST_END,
    S2_MAX_CLOUD_PERCENT,
    S2_MASK_SCL_CLASSES,
)
from src import hotspot_analysis


def test_raw_data_integrity():
    """Verify raw input CSV files are unmodified and have expected dimensions."""
    assert SUOMI_VIIRS_PATH.exists(), "Suomi VIIRS file missing"
    assert NOAA20_VIIRS_PATH.exists(), "NOAA-20 VIIRS file missing"

    df_suomi = pd.read_csv(SUOMI_VIIRS_PATH)
    df_noaa20 = pd.read_csv(NOAA20_VIIRS_PATH)

    assert len(df_suomi) == 65455, f"Unexpected Suomi row count: {len(df_suomi)}"
    assert len(df_noaa20) == 71399, f"Unexpected NOAA-20 row count: {len(df_noaa20)}"
    assert set(df_suomi["confidence"].unique()) == {"l", "n", "h"}
    assert set(df_noaa20["confidence"].unique()) == {"l", "n", "h"}
    assert df_suomi["acq_date"].min() == "2025-10-01"
    assert df_suomi["acq_date"].max() == "2025-11-30"
    assert df_noaa20["acq_date"].min() == "2025-10-01"
    assert df_noaa20["acq_date"].max() == "2025-11-30"

    # Verify no missing coordinates
    assert df_suomi["latitude"].notnull().all() and df_suomi["longitude"].notnull().all()
    assert df_noaa20["latitude"].notnull().all() and df_noaa20["longitude"].notnull().all()


def test_cleaned_cropland_fires():
    """Verify cleaned fire detections meet all filtering requirements."""
    assert CLEANED_FIRES_GEOJSON.exists(), "Cleaned fires GeoJSON missing"
    assert CLEANED_FIRES_CSV.exists(), "Cleaned fires CSV missing"

    gdf = gpd.read_file(CLEANED_FIRES_GEOJSON)

    # 1. Row count validation (exactly 1,872 detections)
    assert len(gdf) == 1872, f"Expected 1,872 cleaned detections, got {len(gdf)}"

    # 2. Confidence validation
    assert set(gdf["confidence"].unique()).issubset(set(RETAINED_CONFIDENCE))
    assert not any(c in EXCLUDED_CONFIDENCE for c in gdf["confidence"].unique())

    # 3. Land cover validation
    assert (gdf["landcover"] == CROPLAND_CLASS_VALUE).all(), "Non-cropland detection found!"

    # 4. Geometry and coordinate validation
    assert gdf.crs.to_string() == "EPSG:4326"
    assert (gdf.geometry.type == "Point").all()

    # 5. Coordinate bounds strictly within Haryana region
    assert gdf.geometry.x.between(74.0, 78.0).all()
    assert gdf.geometry.y.between(27.0, 31.5).all()


def test_district_summary():
    """Verify district summary metrics, counts, and rankings."""
    assert DISTRICT_SUMMARY_CSV.exists(), "District summary CSV missing"
    df_dist = pd.read_csv(DISTRICT_SUMMARY_CSV)

    assert len(df_dist) == 19, f"Expected 19 districts, got {len(df_dist)}"
    assert df_dist["cropland_fire_count"].sum() == 1872, "Total district fires do not sum to 1,872"

    # Top 3 districts verification
    top3 = df_dist.head(3)["district"].tolist()
    assert top3 == ["Jind", "Hisar", "Sirsa"], f"Unexpected top 3 districts: {top3}"

    assert df_dist.loc[df_dist["district"] == "Jind", "cropland_fire_count"].values[0] == 336
    assert df_dist.loc[df_dist["district"] == "Hisar", "cropland_fire_count"].values[0] == 239
    assert df_dist.loc[df_dist["district"] == "Sirsa", "cropland_fire_count"].values[0] == 227

    # Rank consecutive from 1 to 19
    assert list(df_dist["rank"]) == list(range(1, 20))


def test_hexagonal_grid_geometry_and_counts():
    """Verify 5 km hexagonal grid dimensions, area, and detection aggregation."""
    assert HEXGRID_HOTSPOTS_GEOJSON.exists(), "Hexgrid hotspots file missing"
    gdf_hex = gpd.read_file(HEXGRID_HOTSPOTS_GEOJSON)

    assert len(gdf_hex) == 2280, f"Expected 2,280 hex cells, got {len(gdf_hex)}"
    assert "cell_id" in gdf_hex.columns
    assert "fire_count" in gdf_hex.columns
    assert "total_frp" in gdf_hex.columns

    # Reproject to EPSG:32643 to verify metric cell dimensions
    gdf_hex_utm = gdf_hex.to_crs("EPSG:32643")
    poly = gdf_hex_utm.geometry.iloc[0]
    minx, miny, maxx, maxy = poly.bounds
    width = maxx - minx
    height = maxy - miny

    # Flat-to-flat width must equal 5000 m
    assert abs(width - 5000.0) < 1.0, f"Hexagon width {width} m differs from 5000 m"
    # Regular hexagon height = 5000 / cos(30 deg) = 5773.5 m
    assert abs(height - (5000.0 / math.cos(math.radians(30)))) < 2.0

    # Area of 5 km flat-to-flat hexagon = (sqrt(3)/2) * 5000^2 m² = 21.65 km²
    expected_area_km2 = (math.sqrt(3.0) / 2.0) * (5000.0**2) / 1e6
    cell_area_km2 = poly.area / 1e6
    assert abs(cell_area_km2 - expected_area_km2) < 0.05

    # Sum of counts across all cells must match total cleaned fire detections
    total_grid_fires = gdf_hex["fire_count"].sum()
    assert total_grid_fires == 1872, f"Expected grid total 1,872 fires, got {total_grid_fires}"


def test_no_double_counting_across_districts():
    """Ensure spatial join does not assign fire detections to multiple districts."""
    gdf_clean = gpd.read_file(CLEANED_FIRES_GEOJSON)
    gdf_dist = gpd.read_file(HARYANA_DISTRICTS_GEOJSON)
    joined = gpd.sjoin(gdf_clean, gdf_dist[["ADM2_NAME", "geometry"]], how="inner", predicate="intersects")
    assert len(joined) == len(gdf_clean) == 1872


def test_scl_mask_rule_logic():
    """Verify that SCL masking rule correctly flags unwanted classes."""
    # SCL Classes 0..11
    # Unwanted classes: 1 (defective), 3 (shadows), 8 (cloud med), 9 (cloud high), 10 (cirrus), 11 (snow)
    for scl_val in range(12):
        is_masked = scl_val in S2_MASK_SCL_CLASSES
        if scl_val in [1, 3, 8, 9, 10, 11]:
            assert is_masked, f"Class {scl_val} should be masked"
        else:
            assert not is_masked, f"Class {scl_val} should NOT be masked"


def test_sentinel2_parameters():
    """Verify Sentinel-2 parameters match assignment specifications."""
    assert S2_PRE_START == "2025-10-01"
    assert S2_PRE_END == "2025-10-15"
    assert S2_POST_START == "2025-11-12"
    assert S2_POST_END == "2025-11-30"
    assert S2_MAX_CLOUD_PERCENT == 30
    assert set(S2_MASK_SCL_CLASSES) == {1, 3, 8, 9, 10, 11}


def test_final_deliverable_preview_image():
    """Verify outputs/05_composite_preview.png exists and meets dimensions and format."""
    assert COMPOSITE_PREVIEW_PNG.exists(), f"Deliverable missing: {COMPOSITE_PREVIEW_PNG}"

    img = Image.open(COMPOSITE_PREVIEW_PNG)
    width, height = img.size

    # Must be at least 2000 pixels wide
    assert width >= 2000, f"Image width {width} px is less than required 2000 px"
    assert height >= 2000, f"Image height {height} px is less than required 2000 px"
    assert img.mode in ["RGB", "RGBA"], f"Unexpected image mode: {img.mode}"
    assert COMPOSITE_PREVIEW_PNG.stat().st_size > 1_000_000, "File size suspiciously small"
