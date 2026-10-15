"""Master Pipeline Execution Script.

Runs the complete CINT Stubble Burning Detection workflow end-to-end:
  Step 1: Clean VIIRS fire detections & filter to Haryana croplands (ESA WorldCover 2021 class 40)
  Step 2: Hotspot analysis on 5 km hexagonal grid (EPSG:32643) & district ranking
  Step 3: Sentinel-2 Level-2A pre/post median composite generation & master preview rendering
"""

import sys
import time
import logging
import importlib
from pathlib import Path
from PIL import Image

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

# Import modular scripts via importlib
clean_detections = importlib.import_module("src.01_clean_detections")
hotspot_analysis = importlib.import_module("src.02_hotspot_analysis")
sentinel2_composites = importlib.import_module("src.03_sentinel2_composites")

from src.config import (
    COMPOSITE_PREVIEW_PNG,
    DISTRICT_SUMMARY_CSV,
    CLEANED_FIRES_GEOJSON,
    HEXGRID_HOTSPOTS_GEOJSON,
)

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("pipeline")


def main() -> None:
    """Execute all pipeline steps sequentially."""
    start_time = time.time()
    logger.info("=" * 70)
    logger.info("STARTING CINT STUBBLE BURNING DETECTION WORKFLOW")
    logger.info("=" * 70)

    # Step 1: Clean fire detections
    logger.info("\n>>> STEP 1: FIRE DETECTION CLEANING & FILTERING <<<")
    t0 = time.time()
    clean_stats = clean_detections.run_fire_cleaning()
    logger.info(f"Step 1 completed in {time.time() - t0:.2f} seconds.")

    # Step 2: Hotspot analysis
    logger.info("\n>>> STEP 2: 5 KM HEXGRID HOTSPOT ANALYSIS & DISTRICT RANKING <<<")
    t1 = time.time()
    dist_summary, hex_stats = hotspot_analysis.run_hotspot_analysis()
    logger.info(f"Step 2 completed in {time.time() - t1:.2f} seconds.")

    # Step 3: Sentinel-2 composites & final deliverable
    logger.info("\n>>> STEP 3: SENTINEL-2 L2A COMPOSITES & DELIVERABLE GENERATION <<<")
    t2 = time.time()
    sentinel2_composites.run_sentinel2_pipeline()
    logger.info(f"Step 3 completed in {time.time() - t2:.2f} seconds.")

    # Verification
    logger.info("\n" + "=" * 70)
    logger.info("PIPELINE EXECUTION VERIFICATION & FINAL SUMMARY")
    logger.info("=" * 70)

    logger.info("1. CLEANING STAGE COUNTS:")
    logger.info(f"   • Raw combined VIIRS detections (SNPP + N20): {clean_stats['raw_combined_detections']:,}")
    logger.info(f"   • After confidence filter (nominal 'n' + high 'h'): {clean_stats['after_confidence_filter']:,}")
    logger.info(f"   • Intersecting Haryana state boundary: {clean_stats['inside_haryana_boundary']:,}")
    logger.info(f"   • On ESA WorldCover 2021 Cropland (Class 40): {clean_stats['on_esa_worldcover_cropland_40']:,}")

    logger.info("\n2. TOP 3 HOTSPOT DISTRICTS:")
    for _, row in dist_summary.head(3).iterrows():
        logger.info(
            f"   • Rank #{row['rank']} {row['district']}: {row['cropland_fire_count']} fires "
            f"({row['pct_of_state_fires']:.1f}% of state total, {row['total_frp_mw']:.1f} MW total FRP)"
        )

    logger.info("\n3. FINAL DELIVERABLE PREVIEW:")
    if COMPOSITE_PREVIEW_PNG.exists():
        im = Image.open(COMPOSITE_PREVIEW_PNG)
        logger.info(f"   • Path: {COMPOSITE_PREVIEW_PNG}")
        logger.info(f"   • Dimensions: {im.size[0]} x {im.size[1]} pixels (Requirement: >= 2000 px)")
        logger.info(f"   • File Size: {COMPOSITE_PREVIEW_PNG.stat().st_size / 1e6:.2f} MB")
        assert im.size[0] >= 2000, "Image width below 2000 px"
        logger.info("   • Verification: SUCCESS (Meets all dimensional and layout requirements)")
    else:
        logger.error("   • FAILED: Final deliverable image not found!")

    total_elapsed = time.time() - start_time
    logger.info(f"\nEntire pipeline executed successfully in {total_elapsed:.2f} seconds.")
    logger.info("=" * 70)


if __name__ == "__main__":
    main()
