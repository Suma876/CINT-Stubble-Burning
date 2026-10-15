# CINT Stubble Burning Detection & Satellite Monitoring (Autumn 2025)

An end-to-end geospatial Python pipeline for agricultural crop residue (stubble) burning detection, spatial hotspot analysis, and Sentinel-2 Level-2A satellite false-colour composite evaluation across Haryana, India.

---

## 1. Executive Summary & Key Results

During the Autumn post-monsoon harvest window (October 1 – November 30, 2025), active fire detections from NASA FIRMS VIIRS (Suomi NPP and NOAA-20) were ingested, rigorously filtered by quality flags, clipped to the official state boundary of Haryana, and restricted to active agricultural croplands using the ESA WorldCover 2021 (10 m) land cover baseline.

### Data Cleaning Stages & Counts

| Processing Stage | Filter / Operation | Detections Retained | Detections Excluded | Excluded Rationale / Breakdown |
| :--- | :--- | :---: | :---: | :--- |
| **Stage 0: Raw Ingestion** | Combine VIIRS Suomi NPP + NOAA-20 | **136,854** | 0 | Raw Pan-India downloads |
| **Stage 1: Confidence Filter** | Retain nominal (`n`) & high (`h`) | **126,491** | 10,363 | Excluded low (`l`) confidence noise |
| **Stage 2: State Boundary** | Spatial intersect with Haryana (FAO GAUL) | **2,204** | 124,287 | Out-of-state detections across India |
| **Stage 3: Cropland Filter** | ESA WorldCover 2021 Class 40 (Cropland) | **1,872** | 332 | Excluded non-cropland: 123 built-up (50), 93 tree cover (10), 52 bare (60), 30 shrub (20), 29 grassland (30), 5 water (80) |

### Top Hotspot Districts

Spatial aggregation over a 5 km metric hexagonal grid (EPSG:32643) and district boundaries identified the priority agricultural stubble burning hotspots:

| Rank | District | Cropland Fires | Total FRP (MW) | Mean FRP (MW) | Mean Brightness (K) | % of Haryana Cropland Fires |
| :---: | :--- | :---: | :---: | :---: | :---: | :---: |
| **#1** | **Jind** | **336** | **1,486.49** | 4.42 | 335.83 | **17.95%** |
| **#2** | **Hisar** | **239** | **904.59** | 3.78 | 334.83 | **12.77%** |
| **#3** | **Sirsa** | **227** | **934.09** | 4.11 | 330.23 | **12.13%** |
| #4 | Fatehabad | 156 | 721.57 | 4.63 | 335.66 | 8.33% |
| #5 | Sonepat | 148 | 520.72 | 3.52 | 331.43 | 7.91% |
| #6 | Kaithal | 146 | 1,044.28 | 7.15 | 332.49 | 7.80% |

The top three districts (**Jind**, **Hisar**, and **Sirsa**) collectively account for **42.85%** of all agricultural stubble burning detections in Haryana during the Autumn 2025 season.

---

## 2. Primary Deliverable Preview

The final required cartographic deliverable is saved at:
```
outputs/05_composite_preview.png
```
- **Dimensions**: **3000 × 4400 pixels** (Exceeds required ≥ 2000 px).
- **Layout**: Side-by-side pre-fire (`2025-10-01` to `2025-10-15`) and post-fire (`2025-11-12` to `2025-11-30`) panels for each top hotspot district (**Jind**, **Hisar**, **Sirsa**), arranged in one row per district.
- **Cartographic Elements**: Geographically accurate scale bar (calibrated in km), north arrow, exact date ranges, scene counts, district titles with rankings, and complete metadata specifications.
- **Visual Band Combination**: **B12 (SWIR-2) / B8 (NIR) / B4 (Red)** false-colour comparison.

---

## 3. Data Sources & Provenance

1. **NASA FIRMS Active Fires (VIIRS)**:
   - Suomi NPP (`data/raw/fires_suomi_viirs.csv`): 65,455 records (2025-10-01 to 2025-11-30).
   - NOAA-20 (`data/raw/fires_noaa20_viirs.csv`): 71,399 records (2025-10-01 to 2025-11-30).
   - Both datasets capture 375 m resolution thermal anomalies with Fire Radiative Power (FRP), brightness temperature, and confidence categories.

2. **Administrative Boundaries**:
   - Source: United Nations FAO GAUL (Global Administrative Unit Layers) 2015 via Google Earth Engine (`FAO/GAUL/2015/level1` for state and `FAO/GAUL/2015/level2` for districts).
   - Saved locally to `data/boundaries/haryana_state.geojson` and `data/boundaries/haryana_districts.geojson`.

3. **ESA WorldCover 2021 (v200)**:
   - Asset: `ESA/WorldCover/v200` (10 m global land cover map).
   - Class 40 represents **Cropland**. Used to eliminate thermal anomalies from brick kilns, industrial chimneys, urban heat islands, and non-agricultural fires.

4. **Copernicus Sentinel-2 Level-2A Surface Reflectance**:
   - Asset: `COPERNICUS/S2_SR_HARMONIZED`.
   - Pre-fire window: October 1 – October 15, 2025.
   - Post-fire window: November 12 – November 30, 2025.
   - Filtered to scene cloud cover < 30%.
   - Masked using Scene Classification Layer (SCL) for defective pixels (1), shadows (3), clouds (8, 9), cirrus (10), and snow (11).
   - Analysis bands: B2, B3, B4, B8, B11, B12 at 10 m analysis resolution.
   - Consistent surface reflectance stretch: Min [200, 400, 200], Max [3500, 4200, 2500].

---

## 4. Methodology & Workflow

```
[Raw VIIRS CSVS]
   ├── Suomi NPP (65,455)
   └── NOAA-20 (71,399)
            │
            ▼ Combine & Validate (136,854)
            │
            ▼ Filter Confidence: 'n' & 'h' (126,491 retained)
            │
            ▼ Spatial Intersect: Haryana Boundary (2,204 retained)
            │
            ▼ Land Cover Filter: ESA WorldCover Class 40 (1,872 retained)
            │
   ┌────────┴───────────────────────────┐
   ▼                                    ▼
[Hotspot Hexgrid (5 km)]       [District Summary & Ranking]
 - Reproject to EPSG:32643      - Jind (#1: 336 fires)
 - Aggregate Fire Count & FRP   - Hisar (#2: 239 fires)
 - Density per km²              - Sirsa (#3: 227 fires)
                                        │
                                        ▼
                         [Sentinel-2 L2A Median Composites]
                          - Pre-Fire: 2025-10-01 to 2025-10-15
                          - Post-Fire: 2025-11-12 to 2025-11-30
                          - Cloud filter < 30% & SCL Mask
                          - B12 / B8 / B4 False-Colour
                                        │
                                        ▼
                         [outputs/05_composite_preview.png]
```

### False-Colour Interpretation (B12 / B8 / B4)
- **Vibrant Green**: Actively photosynthesizing, healthy crops / green vegetation (strong reflectance in B8 NIR).
- **Dark Rust / Charcoal Brown**: Freshly burned crop residue and stubble burn scars (high SWIR B12 reflection and depleted chlorophyll NIR B8 absorption).
- **Buff / Light Tan**: Unburned bare soil and harvested dry agricultural plots.
- **Dark Blue / Black**: Surface water bodies, canals, and reservoirs.

> **Important Cartographic Note**: This map is a false-colour visual comparison for harvest dynamics and stubble burning monitoring; it is **NOT** a normalized burn severity index (no NBR or dNBR calculated).

---

## 5. Repository Structure

```
CINT-Stubble-Burning/
├── data/
│   ├── raw/
│   │   ├── fires_suomi_viirs.csv        # Raw NASA FIRMS Suomi NPP
│   │   ├── fires_noaa20_viirs.csv       # Raw NASA FIRMS NOAA-20
│   │   └── Readme.txt
│   ├── boundaries/
│   │   ├── haryana_state.geojson        # Official Haryana state polygon
│   │   └── haryana_districts.geojson    # 19 GAUL district polygons
│   └── processed/
│       ├── 04_cleaned_cropland_fires.geojson  # 1,872 cleaned fire points (GeoJSON)
│       └── 04_cleaned_cropland_fires.csv      # Cleaned fire points with attributes
├── outputs/
│   ├── 05_composite_preview.png         # Required deliverable (3000 x 4400 px)
│   ├── district_hotspot_summary.csv     # Ranked district summary
│   ├── haryana_5km_hexgrid_hotspots.geojson # 5 km hexgrid with fire counts & FRP
│   ├── haryana_hotspot_map.png          # Haryana hotspot overview map
│   └── composites/                      # Cached individual district composites
│       ├── Jind_pre.png / Jind_post.png
│       ├── Hisar_pre.png / Hisar_post.png
│       └── Sirsa_pre.png / Sirsa_post.png
├── src/
│   ├── __init__.py
│   ├── config.py                        # Constants, parameters, and filepaths
│   ├── 01_clean_detections.py           # Task 1: Data ingestion, filtering, and EE sampling
│   ├── 02_hotspot_analysis.py           # Task 2: Hexgrid generation and hotspot ranking
│   └── 03_sentinel2_composites.py       # Task 3: S2 composites & deliverable rendering
├── tests/
│   ├── __init__.py
│   └── test_pipeline.py                 # Pytest test suite (integrity, counts, image size)
├── run_pipeline.py                      # Master execution script (end-to-end)
├── requirements.txt                     # Pinned Python package dependencies
├── .gitignore                           # Git ignore rules
└── README.md                            # Comprehensive documentation
```

---

## 6. Installation & Execution

### Prerequisites
- Python 3.12 (or 3.10+)
- Authenticated Google Earth Engine access (Project: `vast-alcove-460907-p0`)

### Setup Virtual Environment
```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

### Reproduce Results End-to-End
To run the complete pipeline from data cleaning through hotspot analysis to the final preview:
```powershell
.\.venv\Scripts\python.exe run_pipeline.py
```

### Run Individual Modular Scripts
```powershell
# Task 1: Fire detection cleaning and land cover filtering
.\.venv\Scripts\python.exe src/01_clean_detections.py

# Task 2: 5 km hexagonal grid hotspot analysis
.\.venv\Scripts\python.exe src/02_hotspot_analysis.py

# Task 3: Sentinel-2 Level-2A composites and master preview map
.\.venv\Scripts\python.exe src/03_sentinel2_composites.py
```

### Run Test Suite
```powershell
.\.venv\Scripts\python.exe -m pytest tests/ -v
```

---

## 7. Assumptions & Known Limitations

1. **Satellite Overpass Frequency & Cloud Gaps**:
   VIIRS sensors on Suomi NPP and NOAA-20 provide daytime (~13:30 local) and nighttime (~01:30 local) thermal observations. Active fire detections capture instantaneous thermal anomalies. Brief agricultural burns occurring outside the satellite overpass window or obscured by thick cloud cover will not be captured by thermal anomaly sensors.
2. **Confidence Thresholding**:
   Low confidence detections (`l`) were excluded to prevent false positives from industrial flare-ups or reflective surfaces. Nominal (`n`) and high (`h`) detections represent confirmed thermal signatures.
3. **10 m Land Cover Filtering**:
   ESA WorldCover 2021 was derived from Sentinel-1 and Sentinel-2 imagery. While highly accurate for field identification, minor misclassifications along field margins or agro-forestry boundaries can occur.
4. **False-Colour Stretch Consistency**:
   The B12/B8/B4 false-colour composite applies identical linear reflectance stretch bounds across both pre- and post-fire imagery. Because it relies on spectral reflection contrast rather than calibrated differential indexing (like dNBR), visual interpretation differentiates burnt scars and bare soil based on the dark rust/charcoal hue and lack of vegetation regrowth.
