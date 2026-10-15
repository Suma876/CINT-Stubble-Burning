"""Configuration and constants for CINT Stubble Burning Detection pipeline."""

from pathlib import Path

# Paths
PROJECT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_DIR / "data"
DATA_RAW_DIR = DATA_DIR / "raw"
DATA_BOUNDARIES_DIR = DATA_DIR / "boundaries"
DATA_PROCESSED_DIR = DATA_DIR / "processed"
OUTPUTS_DIR = PROJECT_DIR / "outputs"

# Raw Data Files
SUOMI_VIIRS_PATH = DATA_RAW_DIR / "fires_suomi_viirs.csv"
NOAA20_VIIRS_PATH = DATA_RAW_DIR / "fires_noaa20_viirs.csv"

# Boundary Paths
HARYANA_STATE_GEOJSON = DATA_BOUNDARIES_DIR / "haryana_state.geojson"
HARYANA_DISTRICTS_GEOJSON = DATA_BOUNDARIES_DIR / "haryana_districts.geojson"

# Processed Paths
CLEANED_FIRES_GEOJSON = DATA_PROCESSED_DIR / "04_cleaned_cropland_fires.geojson"
CLEANED_FIRES_CSV = DATA_PROCESSED_DIR / "04_cleaned_cropland_fires.csv"
HEXGRID_HOTSPOTS_GEOJSON = OUTPUTS_DIR / "haryana_5km_hexgrid_hotspots.geojson"
DISTRICT_SUMMARY_CSV = OUTPUTS_DIR / "district_hotspot_summary.csv"
COMPOSITE_PREVIEW_PNG = OUTPUTS_DIR / "05_composite_preview.png"

# Earth Engine Constants
EE_PROJECT_ID = "vast-alcove-460907-p0"
GAUL_L1_ASSET = "FAO/GAUL/2015/level1"
GAUL_L2_ASSET = "FAO/GAUL/2015/level2"
ESA_WORLDCOVER_ASSET = "ESA/WorldCover/v200"
S2_SR_ASSET = "COPERNICUS/S2_SR_HARMONIZED"

# Coordinate Reference Systems
CRS_WGS84 = "EPSG:4326"
CRS_METRIC = "EPSG:32643"  # UTM Zone 43N

# Fire Filter Criteria
RETAINED_CONFIDENCE = ["n", "h"]
EXCLUDED_CONFIDENCE = ["l"]
CROPLAND_CLASS_VALUE = 40  # ESA WorldCover 2021 Cropland class

# Sentinel-2 Imagery Parameters
S2_PRE_START = "2025-10-01"
S2_PRE_END = "2025-10-15"
S2_POST_START = "2025-11-12"
S2_POST_END = "2025-11-30"

S2_MAX_CLOUD_PERCENT = 30
S2_MASK_SCL_CLASSES = [1, 3, 8, 9, 10, 11]  # Defective, shadows, cloud med/high, cirrus, snow
S2_ANALYSIS_BANDS = ["B2", "B3", "B4", "B8", "B11", "B12"]
S2_FALSE_COLOR_BANDS = ["B12", "B8", "B4"]  # SWIR-2 / NIR / Red

# Visualization Stretch for False-Color Composites (B12, B8, B4 surface reflectance x10000)
VIS_MIN = [200, 400, 200]
VIS_MAX = [3500, 4200, 2500]

# Hotspot Analysis
HEX_SPACING_METERS = 5000  # 5 km regular hexagon grid
