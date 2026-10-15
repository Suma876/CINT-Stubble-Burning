"""Task 3: Sentinel-2 Level-2A Pre/Post Composites and Preview Generation.

Fetches cloud-masked median Sentinel-2 SR Harmonized composites (B12/B8/B4)
for top hotspot districts, clips to district boundaries, and renders the
final deliverable: outputs/05_composite_preview.png (>= 2000 px wide).
"""

import sys
import logging
from pathlib import Path
import io
import math

import ee
import requests
from PIL import Image
import numpy as np
import pandas as pd
import geopandas as gpd
import matplotlib.pyplot as plt
import matplotlib.patches as patches

# Ensure src can be imported
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import (
    EE_PROJECT_ID,
    HARYANA_DISTRICTS_GEOJSON,
    DISTRICT_SUMMARY_CSV,
    OUTPUTS_DIR,
    COMPOSITE_PREVIEW_PNG,
    S2_SR_ASSET,
    GAUL_L2_ASSET,
    S2_PRE_START,
    S2_PRE_END,
    S2_POST_START,
    S2_POST_END,
    S2_MAX_CLOUD_PERCENT,
    S2_MASK_SCL_CLASSES,
    S2_ANALYSIS_BANDS,
    S2_FALSE_COLOR_BANDS,
    VIS_MIN,
    VIS_MAX,
    CRS_METRIC,
    CRS_WGS84,
)

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def init_earth_engine(project_id: str = EE_PROJECT_ID) -> None:
    """Initialize Google Earth Engine."""
    try:
        ee.Initialize(project=project_id)
        logger.info(f"Initialized Earth Engine with project: {project_id}")
    except Exception as exc:
        logger.error(f"Failed to initialize Earth Engine: {exc}")
        raise


def mask_s2_sr(image: ee.Image) -> ee.Image:
    """Mask clouds and unwanted pixels using Sentinel-2 Scene Classification Layer (SCL).
    
    Masks SCL classes 1 (defective), 3 (shadows), 8 (med cloud), 9 (high cloud), 
    10 (cirrus), and 11 (snow).
    """
    scl = image.select("SCL")
    mask = image.select("SCL").neq(1)
    for c in S2_MASK_SCL_CLASSES:
        mask = mask.And(scl.neq(c))
    return image.updateMask(mask)


def build_district_composite(
    district_geom: ee.Geometry,
    start_date: str,
    end_date_inclusive: str,
) -> tuple[ee.Image, int]:
    """Build cloud-masked median composite of Sentinel-2 SR imagery clipped to district."""
    end_date_exclusive = (pd.to_datetime(end_date_inclusive) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")

    collection = (
        ee.ImageCollection(S2_SR_ASSET)
        .filterBounds(district_geom)
        .filterDate(start_date, end_date_exclusive)
        .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", S2_MAX_CLOUD_PERCENT))
    )

    scene_count = collection.size().getInfo()
    if scene_count == 0:
        logger.warning(f"No Sentinel-2 scenes found between {start_date} and {end_date_inclusive}!")
        return None, 0

    masked_col = collection.map(mask_s2_sr).select(S2_ANALYSIS_BANDS)
    median_img = masked_col.median().clip(district_geom)
    return median_img, scene_count


def fetch_composite_image(
    image: ee.Image,
    district_geom: ee.Geometry,
    dimensions: int = 1200,
) -> Image.Image:
    """Fetch RGB visualization of false-color composite from Earth Engine."""
    vis_params = {
        "bands": S2_FALSE_COLOR_BANDS,
        "min": VIS_MIN,
        "max": VIS_MAX,
        "dimensions": dimensions,
        "region": district_geom,
        "format": "png",
    }
    url = image.getThumbURL(vis_params)
    resp = requests.get(url, timeout=90)
    resp.raise_for_status()
    img = Image.open(io.BytesIO(resp.content)).convert("RGB")
    return img


def draw_scale_bar(ax, minx, maxx, miny, maxy, scale_km=10):
    """Draw a professional scale bar with kilometer markings."""
    mean_lat = (miny + maxy) / 2.0
    meters_per_deg_lon = 111320.0 * math.cos(math.radians(mean_lat))
    deg_per_km = 1000.0 / meters_per_deg_lon
    bar_width_deg = scale_km * deg_per_km

    x0 = minx + (maxx - minx) * 0.05
    y0 = miny + (maxy - miny) * 0.06
    x1 = x0 + bar_width_deg

    bg_pad_x = (maxx - minx) * 0.03
    bg_pad_y = (maxy - miny) * 0.03
    rect = patches.FancyBboxPatch(
        (x0 - bg_pad_x * 0.5, y0 - bg_pad_y * 0.9),
        bar_width_deg + bg_pad_x,
        bg_pad_y * 2.6,
        boxstyle="round,pad=0.01",
        facecolor="black",
        edgecolor="#ced4da",
        alpha=0.75,
        zorder=10,
    )
    ax.add_patch(rect)

    mid_x = (x0 + x1) / 2.0
    h = (maxy - miny) * 0.012

    ax.add_patch(patches.Rectangle((x0, y0), mid_x - x0, h, facecolor="#ffffff", edgecolor="#000000", linewidth=0.5, zorder=11))
    ax.add_patch(patches.Rectangle((mid_x, y0), x1 - mid_x, h, facecolor="#ced4da", edgecolor="#000000", linewidth=0.5, zorder=11))

    text_y = y0 + h + (maxy - miny) * 0.007
    ax.text(x0, text_y, "0", ha="center", va="bottom", fontsize=8, color="#ffffff", fontweight="bold", zorder=12)
    ax.text(mid_x, text_y, f"{scale_km // 2}", ha="center", va="bottom", fontsize=8, color="#ffffff", fontweight="bold", zorder=12)
    ax.text(x1, text_y, f"{scale_km} km", ha="center", va="bottom", fontsize=8, color="#ffffff", fontweight="bold", zorder=12)


def draw_north_arrow(ax, minx, maxx, miny, maxy):
    """Draw a clean north arrow on the panel."""
    x = maxx - (maxx - minx) * 0.07
    y = maxy - (maxy - miny) * 0.07
    arrow_len = (maxy - miny) * 0.06

    bg = patches.Circle(
        (x, y - arrow_len * 0.2),
        radius=(maxx - minx) * 0.045,
        facecolor="black",
        edgecolor="#ced4da",
        alpha=0.75,
        zorder=10,
    )
    ax.add_patch(bg)

    ax.annotate(
        "N",
        xy=(x, y),
        xytext=(x, y - arrow_len * 0.65),
        arrowprops=dict(facecolor="#ffffff", edgecolor="#000000", width=2.0, headwidth=6.5, headlength=7.0),
        ha="center",
        va="center",
        fontsize=8.5,
        fontweight="bold",
        color="#ffffff",
        zorder=11,
    )


def render_final_composite_preview(
    districts_data: list[dict],
    output_path: Path = COMPOSITE_PREVIEW_PNG,
) -> None:
    """Render the master composite preview PNG meeting all assignment requirements.
    
    Guarantees:
    - Width >= 2000 px (15 inches at 200 DPI = 3000 pixels)
    - Side-by-side pre-fire and post-fire panels for each selected district
    - One row per district with clear, non-overlapping titles and labels
    - District name, exact date windows, scale bar, north arrow, band combination note, data source
    """
    logger.info(f"Rendering master composite preview to {output_path}...")
    num_districts = len(districts_data)

    # Canvas dimensions: 15.0 in wide x 22.0 in tall @ 200 DPI => 3000 x 4400 pixels
    fig = plt.figure(figsize=(15.0, 22.0), dpi=200, facecolor="#0d1117")

    # Header section with clean clearance
    fig.text(
        0.50,
        0.985,
        "Sentinel-2 Level-2A False-Colour (B12 / B8 / B4) Composite Comparison",
        ha="center",
        va="top",
        fontsize=18,
        fontweight="bold",
        color="#ffffff",
    )
    fig.text(
        0.50,
        0.967,
        "Agricultural Stubble Burning Monitoring Across Priority Hotspot Districts in Haryana, India (Autumn 2025)",
        ha="center",
        va="top",
        fontsize=12,
        fontstyle="italic",
        color="#b0bec5",
    )
    fig.text(
        0.50,
        0.952,
        "Pre-Fire Baseline vs. Post-Fire Landscape | Cloud-Filtered (<30%) SCL-Masked Surface Reflectance Median Composites",
        ha="center",
        va="top",
        fontsize=10,
        color="#90a4ae",
    )

    # Master GridSpec: rows = num_districts, cols = 2
    # Top bound: 0.885 to give abundant room below header (y=0.952)
    # Bottom bound: 0.100 to give room for footer (y=0.015 to 0.085)
    gs = fig.add_gridspec(
        nrows=num_districts,
        ncols=2,
        left=0.08,
        right=0.94,
        top=0.885,
        bottom=0.105,
        wspace=0.10,
        hspace=0.45,
    )

    for row_idx, ddata in enumerate(districts_data):
        dist_name = ddata["district"]
        rank = ddata["rank"]
        fire_count = ddata["cropland_fire_count"]
        pct_state = ddata["pct_state"]
        bounds = ddata["bounds"]  # (minx, miny, maxx, maxy)
        minx, miny, maxx, maxy = bounds
        pre_img = ddata["pre_img"]
        post_img = ddata["post_img"]
        pre_scenes = ddata["pre_scenes"]
        post_scenes = ddata["post_scenes"]
        gdf_poly = ddata["gdf_poly"]

        # Left: Pre-fire panel
        ax_pre = fig.add_subplot(gs[row_idx, 0])
        ax_pre.set_facecolor("#161b22")
        ax_pre.imshow(pre_img, extent=[minx, maxx, miny, maxy], origin="upper", aspect="equal")
        gdf_poly.boundary.plot(ax=ax_pre, color="#ffffff", linewidth=1.2, linestyle="--", alpha=0.9)

        ax_pre.set_title(
            f"PRE-FIRE: {S2_PRE_START} to {S2_PRE_END}\n({pre_scenes} Sentinel-2 L2A Scenes Median)",
            fontsize=9.5,
            fontweight="bold",
            color="#69db7c",
            pad=8,
        )
        scale_val = 15 if (maxx - minx) > 0.65 else 10
        draw_scale_bar(ax_pre, minx, maxx, miny, maxy, scale_km=scale_val)
        draw_north_arrow(ax_pre, minx, maxx, miny, maxy)

        ax_pre.tick_params(colors="#c9d1d9", labelsize=7.5)
        ax_pre.set_xlabel("Longitude (°E)", fontsize=8, color="#c9d1d9")
        ax_pre.set_ylabel("Latitude (°N)", fontsize=8, color="#c9d1d9")
        for spine in ax_pre.spines.values():
            spine.set_color("#30363d")

        # Right: Post-fire panel
        ax_post = fig.add_subplot(gs[row_idx, 1])
        ax_post.set_facecolor("#161b22")
        ax_post.imshow(post_img, extent=[minx, maxx, miny, maxy], origin="upper", aspect="equal")
        gdf_poly.boundary.plot(ax=ax_post, color="#ffffff", linewidth=1.2, linestyle="--", alpha=0.9)

        ax_post.set_title(
            f"POST-FIRE: {S2_POST_START} to {S2_POST_END}\n({post_scenes} Sentinel-2 L2A Scenes Median)",
            fontsize=9.5,
            fontweight="bold",
            color="#ff6b6b",
            pad=8,
        )
        draw_scale_bar(ax_post, minx, maxx, miny, maxy, scale_km=scale_val)
        draw_north_arrow(ax_post, minx, maxx, miny, maxy)

        ax_post.tick_params(colors="#c9d1d9", labelsize=7.5)
        ax_post.set_xlabel("Longitude (°E)", fontsize=8, color="#c9d1d9")
        ax_post.set_ylabel("Latitude (°N)", fontsize=8, color="#c9d1d9")
        for spine in ax_post.spines.values():
            spine.set_color("#30363d")

    # Render figure to calculate exact axis positions for row banners
    fig.canvas.draw()

    for row_idx, ddata in enumerate(districts_data):
        dist_name = ddata["district"]
        rank = ddata["rank"]
        fire_count = ddata["cropland_fire_count"]
        pct_state = ddata["pct_state"]

        ax_left = fig.axes[row_idx * 2]
        pos = ax_left.get_position()
        banner_y = pos.y1 + 0.038  # Position cleanly above panel title

        fig.text(
            0.51,
            banner_y,
            f"Row {row_idx + 1} — District: {dist_name}  (Hotspot Rank #{rank} | {fire_count:,} Cropland Fires | {pct_state:.1f}% of Haryana Cropland Detections)",
            ha="center",
            va="bottom",
            fontsize=12,
            fontweight="bold",
            color="#ffe066",
            bbox=dict(boxstyle="round,pad=0.35", facecolor="#1a202c", edgecolor="#ffd166", linewidth=1.0),
        )

    # Bottom Metadata Box (below y=0.08)
    metadata_text = (
        "SPECIFICATIONS & METADATA:\n"
        "• Data Source: European Space Agency (ESA) Copernicus Sentinel-2 Level-2A Surface Reflectance (COPERNICUS/S2_SR_HARMONIZED), 2025.\n"
        "• Band Combination: B12 (SWIR-2, ~2190 nm) / B8 (NIR, ~842 nm) / B4 (Red, ~665 nm) — displayed in RGB at 10 m analysis resolution.\n"
        "• Quality & Cloud Filtering: Scenes filtered to CLOUDY_PIXEL_PERCENTAGE < 30%. Scene Classification Layer (SCL) classes 1, 3, 8, 9, 10, 11 masked.\n"
        "• Consistent Visualization Stretch: Fixed surface reflectance thresholds (Min: [200, 400, 200], Max: [3500, 4200, 2500]) applied identically across all pre/post panels.\n"
        "• Visual Interpretation: [Vibrant Green] = Actively vegetated crops | [Dark Rust / Charcoal Brown] = Burnt stubble / crop residue burn scars | [Buff / Tan] = Bare soil / harvested unburnt plots.\n"
        "• Disclaimer: This is a false-colour visual comparison for agricultural monitoring; it is NOT a normalized burn severity index (no NBR or dNBR calculated)."
    )

    fig.text(
        0.51,
        0.045,
        metadata_text,
        ha="center",
        va="center",
        fontsize=8.2,
        color="#e0e0e0",
        bbox=dict(boxstyle="round,pad=0.6", facecolor="#161b22", edgecolor="#30363d", linewidth=1.2),
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=200, facecolor=fig.get_facecolor(), edgecolor="none")
    plt.close(fig)

    # Write binary bytes to disk with retry for Windows file locks
    import time
    for attempt in range(5):
        try:
            with open(str(output_path), "wb") as f:
                f.write(buf.getvalue())
            break
        except OSError:
            time.sleep(0.5)

    # Verify generated image properties
    img_saved = Image.open(str(output_path))
    w, h = img_saved.size
    logger.info(f"Generated final preview map: {output_path} ({w} x {h} px, size: {output_path.stat().st_size / 1e6:.2f} MB)")
    if w < 2000:
        raise ValueError(f"Output preview width {w} px is less than required 2000 pixels!")


def run_sentinel2_pipeline() -> None:
    """Execute Task 3: build composites for top districts and render final preview."""
    init_earth_engine()

    if not DISTRICT_SUMMARY_CSV.exists():
        raise FileNotFoundError(f"District summary CSV missing: {DISTRICT_SUMMARY_CSV}. Run 02_hotspot_analysis.py first.")

    df_summary = pd.read_csv(DISTRICT_SUMMARY_CSV)
    top_districts = df_summary.head(3)  # Top 3 districts: Jind, Hisar, Sirsa
    logger.info(f"Top 3 hotspot districts selected: {top_districts['district'].tolist()}")

    gdf_districts = gpd.read_file(HARYANA_DISTRICTS_GEOJSON)
    ee_districts = ee.FeatureCollection(GAUL_L2_ASSET).filter(ee.Filter.eq("ADM1_NAME", "Haryana"))

    cache_dir = OUTPUTS_DIR / "composites"
    cache_dir.mkdir(parents=True, exist_ok=True)

    districts_data = []

    for _, row in top_districts.iterrows():
        dname = row["district"]
        rank = row["rank"]
        count = row["cropland_fire_count"]
        pct = row["pct_of_state_fires"]

        logger.info(f"Processing District #{rank}: {dname} ({count} fires)...")

        ee_geom = ee_districts.filter(ee.Filter.eq("ADM2_NAME", dname)).geometry()
        gdf_poly = gdf_districts[gdf_districts["ADM2_NAME"] == dname]
        bounds = gdf_poly.total_bounds

        # Pre-fire composite
        pre_cache = cache_dir / f"{dname}_pre.png"
        pre_img, pre_scenes = None, 0
        if pre_cache.exists():
            logger.info(f"Loading cached pre-fire image for {dname} from {pre_cache}")
            pre_img = Image.open(pre_cache).convert("RGB")
            pre_col = (
                ee.ImageCollection(S2_SR_ASSET)
                .filterBounds(ee_geom)
                .filterDate(S2_PRE_START, "2025-10-16")
                .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", S2_MAX_CLOUD_PERCENT))
            )
            pre_scenes = pre_col.size().getInfo()
        else:
            logger.info(f"Building pre-fire composite for {dname} ({S2_PRE_START} to {S2_PRE_END})...")
            pre_ee_img, pre_scenes = build_district_composite(ee_geom, S2_PRE_START, S2_PRE_END)
            pre_img = fetch_composite_image(pre_ee_img, ee_geom, dimensions=1200)
            pre_img.save(pre_cache)
            logger.info(f"Saved pre-fire composite to {pre_cache}")

        # Post-fire composite
        post_cache = cache_dir / f"{dname}_post.png"
        post_img, post_scenes = None, 0
        if post_cache.exists():
            logger.info(f"Loading cached post-fire image for {dname} from {post_cache}")
            post_img = Image.open(post_cache).convert("RGB")
            post_col = (
                ee.ImageCollection(S2_SR_ASSET)
                .filterBounds(ee_geom)
                .filterDate(S2_POST_START, "2025-12-01")
                .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", S2_MAX_CLOUD_PERCENT))
            )
            post_scenes = post_col.size().getInfo()
        else:
            logger.info(f"Building post-fire composite for {dname} ({S2_POST_START} to {S2_POST_END})...")
            post_ee_img, post_scenes = build_district_composite(ee_geom, S2_POST_START, S2_POST_END)
            post_img = fetch_composite_image(post_ee_img, ee_geom, dimensions=1200)
            post_img.save(post_cache)
            logger.info(f"Saved post-fire composite to {post_cache}")

        districts_data.append({
            "district": dname,
            "rank": rank,
            "cropland_fire_count": count,
            "pct_state": pct,
            "bounds": bounds,
            "pre_img": pre_img,
            "post_img": post_img,
            "pre_scenes": pre_scenes,
            "post_scenes": post_scenes,
            "gdf_poly": gdf_poly,
        })

    render_final_composite_preview(districts_data, output_path=COMPOSITE_PREVIEW_PNG)


if __name__ == "__main__":
    run_sentinel2_pipeline()
