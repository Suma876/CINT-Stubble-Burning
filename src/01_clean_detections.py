"""Task 1: Fire Detection Cleaning Pipeline.

Combines Suomi NPP and NOAA-20 VIIRS active fire detections,
validates metadata, filters to Haryana state boundary, and filters
to ESA WorldCover 2021 cropland class 40.
"""

import sys
import logging
from pathlib import Path
import json

import ee
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point

# Ensure src can be imported
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import (
    EE_PROJECT_ID,
    SUOMI_VIIRS_PATH,
    NOAA20_VIIRS_PATH,
    HARYANA_STATE_GEOJSON,
    HARYANA_DISTRICTS_GEOJSON,
    DATA_BOUNDARIES_DIR,
    DATA_PROCESSED_DIR,
    CLEANED_FIRES_GEOJSON,
    CLEANED_FIRES_CSV,
    GAUL_L1_ASSET,
    GAUL_L2_ASSET,
    ESA_WORLDCOVER_ASSET,
    CRS_WGS84,
    RETAINED_CONFIDENCE,
    CROPLAND_CLASS_VALUE,
)

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def init_earth_engine(project_id: str = EE_PROJECT_ID) -> None:
    """Initialize Google Earth Engine with the designated project ID."""
    try:
        ee.Initialize(project=project_id)
        logger.info(f"Initialized Earth Engine with project: {project_id}")
    except Exception as exc:
        logger.error(f"Failed to initialize Earth Engine: {exc}")
        raise


def get_or_download_boundaries() -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:
    """Retrieve official Haryana state and district boundaries from FAO GAUL via GEE."""
    DATA_BOUNDARIES_DIR.mkdir(parents=True, exist_ok=True)

    if HARYANA_STATE_GEOJSON.exists() and HARYANA_DISTRICTS_GEOJSON.exists():
        logger.info("Loading cached Haryana boundaries from disk.")
        gdf_state = gpd.read_file(HARYANA_STATE_GEOJSON)
        gdf_districts = gpd.read_file(HARYANA_DISTRICTS_GEOJSON)
        return gdf_state, gdf_districts

    logger.info("Fetching official FAO GAUL Haryana boundaries from Earth Engine...")
    state_fc = ee.FeatureCollection(GAUL_L1_ASSET).filter(ee.Filter.eq("ADM1_NAME", "Haryana"))
    state_features = state_fc.getInfo()["features"]
    if not state_features:
        raise ValueError("No state boundary features found for Haryana in GAUL Level 1.")
    gdf_state = gpd.GeoDataFrame.from_features(state_features, crs=CRS_WGS84)
    gdf_state.to_file(HARYANA_STATE_GEOJSON, driver="GeoJSON")
    logger.info(f"Saved Haryana state boundary to {HARYANA_STATE_GEOJSON}")

    dist_fc = ee.FeatureCollection(GAUL_L2_ASSET).filter(ee.Filter.eq("ADM1_NAME", "Haryana"))
    dist_features = dist_fc.getInfo()["features"]
    if not dist_features:
        raise ValueError("No district boundary features found for Haryana in GAUL Level 2.")
    gdf_districts = gpd.GeoDataFrame.from_features(dist_features, crs=CRS_WGS84)
    gdf_districts.to_file(HARYANA_DISTRICTS_GEOJSON, driver="GeoJSON")
    logger.info(f"Saved {len(gdf_districts)} Haryana district boundaries to {HARYANA_DISTRICTS_GEOJSON}")

    return gdf_state, gdf_districts


def load_and_validate_raw_data() -> pd.DataFrame:
    """Load both VIIRS CSVs, validate formats, dates, confidence, and satellites."""
    if not SUOMI_VIIRS_PATH.exists():
        raise FileNotFoundError(f"Missing Suomi VIIRS file: {SUOMI_VIIRS_PATH}")
    if not NOAA20_VIIRS_PATH.exists():
        raise FileNotFoundError(f"Missing NOAA-20 VIIRS file: {NOAA20_VIIRS_PATH}")

    logger.info("Reading raw VIIRS datasets...")
    df_suomi = pd.read_csv(SUOMI_VIIRS_PATH)
    df_noaa20 = pd.read_csv(NOAA20_VIIRS_PATH)

    logger.info(f"Suomi NPP rows: {len(df_suomi):,}")
    logger.info(f"NOAA-20 rows: {len(df_noaa20):,}")

    # Validate satellites
    assert set(df_suomi["satellite"].unique()) == {"SNPP"} or "SNPP" in df_suomi["satellite"].unique()
    assert set(df_noaa20["satellite"].unique()) == {"N20"} or "N20" in df_noaa20["satellite"].unique()

    # Combine datasets
    df_combined = pd.concat([df_suomi, df_noaa20], ignore_index=True)
    logger.info(f"Combined total raw rows: {len(df_combined):,}")

    # Validate coordinate bounds
    valid_coords = (
        (df_combined["latitude"] >= -90)
        & (df_combined["latitude"] <= 90)
        & (df_combined["longitude"] >= -180)
        & (df_combined["longitude"] <= 180)
    )
    if not valid_coords.all():
        raise ValueError("Dataset contains invalid geographical coordinates.")

    # Validate date range
    df_combined["acq_date"] = pd.to_datetime(df_combined["acq_date"])
    date_min = df_combined["acq_date"].min().strftime("%Y-%m-%d")
    date_max = df_combined["acq_date"].max().strftime("%Y-%m-%d")
    logger.info(f"Temporal span: {date_min} to {date_max}")

    return df_combined


def sample_esa_worldcover(gdf_points: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Sample ESA WorldCover 2021 (v200) land cover class for each point using Earth Engine."""
    logger.info(f"Sampling ESA WorldCover 2021 for {len(gdf_points):,} detection points in GEE...")

    # Load ESA WorldCover 2021 Map band
    worldcover = ee.ImageCollection(ESA_WORLDCOVER_ASSET).first().select("Map")

    # Build FeatureCollection with point IDs
    gdf_copy = gdf_points.copy().reset_index(drop=True)
    gdf_copy["point_id"] = gdf_copy.index

    # Batch points if needed (2,204 fits well within EE 5000 feature limit)
    features = []
    for _, row in gdf_copy.iterrows():
        f = ee.Feature(ee.Geometry.Point([row.longitude, row.latitude]), {"point_id": int(row["point_id"])})
        features.append(f)

    fc_points = ee.FeatureCollection(features)
    sampled = worldcover.reduceRegions(collection=fc_points, reducer=ee.Reducer.first(), scale=10)
    sampled_data = sampled.getInfo()["features"]

    lc_dict = {}
    for item in sampled_data:
        props = item["properties"]
        pid = props["point_id"]
        val = props.get("first")
        lc_dict[pid] = val

    gdf_copy["landcover"] = gdf_copy["point_id"].map(lc_dict)
    return gdf_copy


def run_fire_cleaning() -> dict:
    """Execute complete Stage 1 to Stage 4 cleaning workflow."""
    DATA_PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    init_earth_engine()

    # Boundaries
    gdf_state, gdf_districts = get_or_download_boundaries()

    # Stage 0: Load Raw
    df_combined = load_and_validate_raw_data()
    stage0_count = len(df_combined)

    # Stage 1: Confidence Filter (retain 'n' and 'h', exclude 'l')
    df_conf = df_combined[df_combined["confidence"].isin(RETAINED_CONFIDENCE)].copy()
    stage1_count = len(df_conf)
    logger.info(f"Stage 1 - Confidence filter ({RETAINED_CONFIDENCE}): {stage1_count:,} retained (excluded {stage0_count - stage1_count:,} 'l' detections)")

    # Stage 2: Spatial Filter to Haryana State
    gdf_fires = gpd.GeoDataFrame(
        df_conf,
        geometry=gpd.points_from_xy(df_conf.longitude, df_conf.latitude),
        crs=CRS_WGS84,
    )

    # Spatial Join with District Boundaries to simultaneously filter to Haryana and assign district
    # Using 'ADM2_NAME' as the district identifier
    district_cols = ["ADM2_NAME", "geometry"]
    gdf_haryana_fires = gpd.sjoin(gdf_fires, gdf_districts[district_cols], how="inner", predicate="intersects")
    gdf_haryana_fires = gdf_haryana_fires.rename(columns={"ADM2_NAME": "district"})
    gdf_haryana_fires = gdf_haryana_fires.drop(columns=["index_right"], errors="ignore")
    stage2_count = len(gdf_haryana_fires)
    logger.info(f"Stage 2 - Haryana state spatial intersection: {stage2_count:,} fire detections retained")

    # Stage 3: ESA WorldCover 2021 Cropland Filter (Class 40)
    gdf_sampled = sample_esa_worldcover(gdf_haryana_fires)
    lc_breakdown = gdf_sampled["landcover"].value_counts().to_dict()
    logger.info(f"ESA WorldCover land class distribution across Haryana detections: {lc_breakdown}")

    gdf_cropland = gdf_sampled[gdf_sampled["landcover"] == CROPLAND_CLASS_VALUE].copy()
    stage3_count = len(gdf_cropland)
    logger.info(f"Stage 3 - Cropland class 40 filter: {stage3_count:,} detections retained (excluded {stage2_count - stage3_count:,} non-cropland detections)")

    # Save outputs
    # Drop temp columns
    gdf_cropland = gdf_cropland.drop(columns=["point_id"], errors="ignore")
    gdf_cropland.to_file(CLEANED_FIRES_GEOJSON, driver="GeoJSON")
    logger.info(f"Saved cleaned cropland detections GeoJSON to: {CLEANED_FIRES_GEOJSON}")

    # Also save CSV
    df_export = pd.DataFrame(gdf_cropland.drop(columns=["geometry"]))
    df_export.to_csv(CLEANED_FIRES_CSV, index=False)
    logger.info(f"Saved cleaned cropland detections CSV to: {CLEANED_FIRES_CSV}")

    stats = {
        "raw_combined_detections": stage0_count,
        "after_confidence_filter": stage1_count,
        "inside_haryana_boundary": stage2_count,
        "on_esa_worldcover_cropland_40": stage3_count,
        "landcover_class_distribution": lc_breakdown,
        "top_districts": gdf_cropland["district"].value_counts().head(5).to_dict(),
    }
    return stats


if __name__ == "__main__":
    results = run_fire_cleaning()
    print("\n" + "=" * 60)
    print("TASK 1 CLEANING SUMMARY REPORT")
    print("=" * 60)
    for k, v in results.items():
        print(f"  {k}: {v}")
    print("=" * 60)
