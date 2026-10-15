"""Task 2: Hotspot Analysis Pipeline.

Reprojects cleaned fire detections to EPSG:32643, builds a 5 km hexagonal grid,
aggregates detection counts and FRP per cell, summarizes detections by district,
and exports reproducible tabular and geospatial outputs.
"""

import sys
import logging
from pathlib import Path
import math

import numpy as np
import pandas as pd
import geopandas as gpd
from shapely.geometry import Polygon
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors

# Ensure src can be imported
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import (
    CLEANED_FIRES_GEOJSON,
    HARYANA_STATE_GEOJSON,
    HARYANA_DISTRICTS_GEOJSON,
    OUTPUTS_DIR,
    HEXGRID_HOTSPOTS_GEOJSON,
    DISTRICT_SUMMARY_CSV,
    CRS_WGS84,
    CRS_METRIC,
    HEX_SPACING_METERS,
)

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def create_hexagonal_grid(
    gdf_boundary: gpd.GeoDataFrame,
    spacing: float = HEX_SPACING_METERS,
    crs: str = CRS_METRIC,
) -> gpd.GeoDataFrame:
    """Generate a regular hexagonal grid covering the extent of gdf_boundary.
    
    Parameters:
    - gdf_boundary: GeoDataFrame in target CRS (EPSG:32643)
    - spacing: Flat-to-flat distance of regular hexagons (meters)
    - crs: Target projection
    """
    logger.info(f"Generating {spacing / 1000:.1f} km hexagonal grid in {crs}...")
    minx, miny, maxx, maxy = gdf_boundary.total_bounds

    # Circumradius r for flat-to-flat width = spacing
    # flat-to-flat width d = sqrt(3) * r => r = spacing / sqrt(3)
    r = spacing / math.sqrt(3.0)
    dx = spacing
    dy = 1.5 * r

    # Buffer the bounds slightly to ensure full coverage
    buffer = spacing
    x_coords = np.arange(minx - buffer, maxx + buffer, dx)
    y_coords = np.arange(miny - buffer, maxy + buffer, dy)

    hexagons = []
    cell_ids = []
    cell_idx = 0

    for row_idx, y in enumerate(y_coords):
        x_offset = (dx / 2.0) if (row_idx % 2 == 1) else 0.0
        for x in x_coords:
            cx = x + x_offset
            cy = y
            # Pointy-topped hexagon vertices
            # angles: 30, 90, 150, 210, 270, 330 deg
            angles = [math.radians(30 + 60 * i) for i in range(6)]
            poly_points = [(cx + r * math.cos(a), cy + r * math.sin(a)) for a in angles]
            hex_poly = Polygon(poly_points)
            hexagons.append(hex_poly)
            cell_ids.append(f"HEX_{cell_idx:05d}")
            cell_idx += 1

    gdf_grid = gpd.GeoDataFrame({"cell_id": cell_ids, "geometry": hexagons}, crs=crs)

    # Filter to cells that intersect the boundary polygon
    boundary_geom = gdf_boundary.unary_union
    gdf_grid = gdf_grid[gdf_grid.intersects(boundary_geom)].copy().reset_index(drop=True)
    logger.info(f"Generated {len(gdf_grid):,} hexagonal cells intersecting the boundary.")
    return gdf_grid


def run_hotspot_analysis() -> tuple[pd.DataFrame, gpd.GeoDataFrame]:
    """Execute Task 2 Hotspot Analysis."""
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

    if not CLEANED_FIRES_GEOJSON.exists():
        raise FileNotFoundError(f"Cleaned detections not found: {CLEANED_FIRES_GEOJSON}. Run 01_clean_detections.py first.")

    # 1. Load cleaned fires and reproject to EPSG:32643
    logger.info(f"Loading cleaned cropland fires from {CLEANED_FIRES_GEOJSON}...")
    gdf_fires = gpd.read_file(CLEANED_FIRES_GEOJSON)
    logger.info(f"Loaded {len(gdf_fires):,} cleaned cropland fire detections.")
    gdf_fires_utm = gdf_fires.to_crs(CRS_METRIC)

    # 2. Load Haryana boundaries in EPSG:32643
    gdf_state = gpd.read_file(HARYANA_STATE_GEOJSON).to_crs(CRS_METRIC)
    gdf_districts = gpd.read_file(HARYANA_DISTRICTS_GEOJSON).to_crs(CRS_METRIC)

    # 3. Build 5 km hexagonal grid
    gdf_hex = create_hexagonal_grid(gdf_state, spacing=HEX_SPACING_METERS, crs=CRS_METRIC)

    # 4. Count detections per grid cell and sum FRP
    logger.info("Performing spatial join between hex grid and detections...")
    joined = gpd.sjoin(gdf_fires_utm, gdf_hex[["cell_id", "geometry"]], how="inner", predicate="within")

    agg_stats = (
        joined.groupby("cell_id")
        .agg(
            fire_count=("latitude", "count"),
            total_frp=("frp", "sum"),
            mean_frp=("frp", "mean"),
            mean_brightness=("brightness", "mean"),
        )
        .reset_index()
    )

    # Merge aggregated stats into the hexagonal grid
    gdf_hex_stats = gdf_hex.merge(agg_stats, on="cell_id", how="left")
    gdf_hex_stats["fire_count"] = gdf_hex_stats["fire_count"].fillna(0).astype(int)
    gdf_hex_stats["total_frp"] = gdf_hex_stats["total_frp"].fillna(0.0).round(2)
    gdf_hex_stats["mean_frp"] = gdf_hex_stats["mean_frp"].fillna(0.0).round(2)
    gdf_hex_stats["mean_brightness"] = gdf_hex_stats["mean_brightness"].fillna(0.0).round(2)

    # Cell area in km² (approx 21.65 km² for 5km hex)
    gdf_hex_stats["area_sqkm"] = (gdf_hex_stats.geometry.area / 1e6).round(2)
    gdf_hex_stats["fire_density_per_sqkm"] = (
        gdf_hex_stats["fire_count"] / gdf_hex_stats["area_sqkm"]
    ).round(4)

    # Export hex grid to GeoJSON in WGS84 for broad compatibility
    gdf_hex_wgs84 = gdf_hex_stats.to_crs(CRS_WGS84)
    gdf_hex_wgs84.to_file(HEXGRID_HOTSPOTS_GEOJSON, driver="GeoJSON")
    logger.info(f"Saved hexagonal hotspot grid to {HEXGRID_HOTSPOTS_GEOJSON}")

    # 5. Summarize detections by district
    logger.info("Computing district-level summary...")
    total_cleaned_fires = len(gdf_fires)
    dist_summary = (
        gdf_fires.groupby("district")
        .agg(
            cropland_fire_count=("latitude", "count"),
            total_frp_mw=("frp", "sum"),
            mean_frp_mw=("frp", "mean"),
            mean_brightness_k=("brightness", "mean"),
            high_confidence_count=("confidence", lambda s: (s == "h").sum()),
            nominal_confidence_count=("confidence", lambda s: (s == "n").sum()),
        )
        .reset_index()
    )

    dist_summary["pct_of_state_fires"] = (
        (dist_summary["cropland_fire_count"] / total_cleaned_fires) * 100
    ).round(2)
    dist_summary["total_frp_mw"] = dist_summary["total_frp_mw"].round(2)
    dist_summary["mean_frp_mw"] = dist_summary["mean_frp_mw"].round(2)
    dist_summary["mean_brightness_k"] = dist_summary["mean_brightness_k"].round(2)

    # Rank districts
    dist_summary = dist_summary.sort_values(
        by=["cropland_fire_count", "total_frp_mw"], ascending=[False, False]
    ).reset_index(drop=True)
    dist_summary["rank"] = range(1, len(dist_summary) + 1)

    # Save summary CSV
    dist_summary.to_csv(DISTRICT_SUMMARY_CSV, index=False)
    logger.info(f"Saved district hotspot summary to {DISTRICT_SUMMARY_CSV}")

    # 6. Render an overview Hotspot Map
    render_hotspot_overview_map(gdf_hex_stats, gdf_districts, dist_summary)

    return dist_summary, gdf_hex_stats


def render_hotspot_overview_map(
    gdf_hex_utm: gpd.GeoDataFrame,
    gdf_districts_utm: gpd.GeoDataFrame,
    dist_summary: pd.DataFrame,
) -> None:
    """Render a clean 5 km hexgrid hotspot map for Haryana."""
    map_path = OUTPUTS_DIR / "haryana_hotspot_map.png"
    logger.info(f"Rendering hotspot overview map to {map_path}...")

    fig, ax = plt.subplots(figsize=(10, 11), dpi=200)

    # Background district shapes
    gdf_districts_utm.plot(
        ax=ax,
        color="#f8f9fa",
        edgecolor="#adb5bd",
        linewidth=0.8,
        zorder=1,
    )

    # Hex cells with fires > 0
    active_hex = gdf_hex_utm[gdf_hex_utm["fire_count"] > 0]
    zero_hex = gdf_hex_utm[gdf_hex_utm["fire_count"] == 0]

    # Outline of zero cells
    zero_hex.plot(
        ax=ax,
        facecolor="none",
        edgecolor="#dee2e6",
        linewidth=0.3,
        linestyle=":",
        zorder=2,
    )

    # Color active hex cells
    active_hex.plot(
        column="fire_count",
        ax=ax,
        cmap="YlOrRd",
        legend=True,
        legend_kwds={
            "label": "Cropland Fire Detections per 5 km Cell",
            "orientation": "horizontal",
            "shrink": 0.6,
            "pad": 0.04,
        },
        edgecolor="#d9534f",
        linewidth=0.4,
        zorder=3,
    )

    # Overlay district boundaries
    gdf_districts_utm.plot(
        ax=ax,
        facecolor="none",
        edgecolor="#343a40",
        linewidth=1.2,
        zorder=4,
    )

    # Label top 3 districts
    top3_names = dist_summary.head(3)["district"].tolist()
    for _, row in gdf_districts_utm.iterrows():
        name = row["ADM2_NAME"]
        centroid = row.geometry.centroid
        if name in top3_names:
            rank = dist_summary.loc[dist_summary["district"] == name, "rank"].values[0]
            count = dist_summary.loc[dist_summary["district"] == name, "cropland_fire_count"].values[0]
            ax.annotate(
                f"#{rank} {name}\n({count} fires)",
                xy=(centroid.x, centroid.y),
                xytext=(0, 0),
                textcoords="offset points",
                ha="center",
                va="center",
                fontsize=9,
                fontweight="bold",
                color="#b7094c",
                bbox=dict(boxstyle="round,pad=0.3", fc="#ffffff", ec="#b7094c", alpha=0.9),
                zorder=5,
            )
        else:
            ax.annotate(
                name,
                xy=(centroid.x, centroid.y),
                xytext=(0, 0),
                textcoords="offset points",
                ha="center",
                va="center",
                fontsize=6.5,
                color="#495057",
                zorder=4,
            )

    ax.set_title(
        "Haryana Agricultural Stubble Burning Hotspots (Oct–Nov 2025)\n"
        "5 km Hexagonal Grid Detections (VIIRS SNPP & NOAA-20 on ESA WorldCover Cropland)",
        fontsize=11,
        fontweight="bold",
        pad=12,
    )
    ax.set_axis_off()
    plt.tight_layout()
    try:
        plt.savefig(str(map_path), dpi=200, bbox_inches="tight")
        logger.info(f"Saved hotspot map to {map_path}")
    except Exception as exc:
        logger.warning(f"Note: Could not update secondary overview map: {exc}")
    finally:
        plt.close()


if __name__ == "__main__":
    summary, _ = run_hotspot_analysis()
    print("\n" + "=" * 60)
    print("TASK 2 DISTRICT HOTSPOT SUMMARY (TOP DISTRICTS)")
    print("=" * 60)
    print(summary.head(10).to_string(index=False))
    print("=" * 60)
