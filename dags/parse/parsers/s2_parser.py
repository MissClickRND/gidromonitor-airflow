from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import ee

from utils.file_utils import S2_BANDS_CONFIG
from utils.geojson_utils import geojson_to_ee_geometry
from utils.gee_tiled_download import tiled_download_and_upload

logger = logging.getLogger(__name__)

GEE_PROJECT = os.getenv("GEE_PROJECT")
GEE_KEY_PATH = os.getenv("GEE_KEY_PATH")
YC_BUCKET = os.getenv("YC_BUCKET")
YANDEX_CONN_ID = os.getenv("YANDEX_CONN_ID")

S2_COLLECTION_ID = os.getenv("S2_COLLECTION_ID", "COPERNICUS/S2_SR_HARMONIZED")

REFLECTANCE_BANDS = ["B2", "B3", "B4", "B8", "B11", "B12"]
MASK_BANDS = ["SCL"]
EXPORT_BANDS = REFLECTANCE_BANDS + MASK_BANDS

CLOUD_SCL_CLASSES = (3, 8, 9, 10)
SCL_MAX_CLASS = 11

SEARCH_WINDOW_DAYS = 4
DATE_WEIGHT_PCT_PER_DAY = 1.0

MAX_GRANULE_CLOUD_PCT = 80

MAX_AOI_CLOUD_PCT = 5
MIN_AOI_COVERAGE_PCT = 99.5

MAX_PASSES_TO_TRY = 3
TOP_SCENES = 40

EXPORT_SCALE = 10
EXPORT_CRS = "EPSG:32652"
STATS_SCALE = 20
CLOUD_BUFFER_M = 60
VALIDATE_SCL = False
MAX_PIXELS = int(1e10)

_EE_READY = False


def init_ee() -> None:
    global _EE_READY
    if _EE_READY:
        return

    with open(os.environ["GEE_KEY_PATH"]) as f:
        service_account_info = json.load(f)

    credentials = ee.ServiceAccountCredentials(
        email=service_account_info['client_email'],
        key_data=service_account_info['private_key']
    )
    ee.Initialize(credentials, project=GEE_PROJECT)
    _EE_READY = True


_DATE_FORMATS = ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ",
                 "%Y-%m-%d %H:%M:%S", "%Y/%m/%d", "%d.%m.%Y")


def _parse_date(value: Any, label: str) -> ee.Date:
    if isinstance(value, ee.Date):
        return value
    text = str(value).strip()
    for fmt in _DATE_FORMATS:
        try:
            dt = datetime.strptime(text, fmt)
        except ValueError:
            continue
        return ee.Date(dt.strftime("%Y-%m-%dT%H:%M:%S"))
    raise ValueError(f"{label}: не удалось разобрать дату '{value}' (ожидается YYYY-MM-DD)")


def scl_cloud_mask(scl: ee.Image, buffer_m: float = CLOUD_BUFFER_M) -> ee.Image:
    is_cloud = scl.eq(CLOUD_SCL_CLASSES[0])
    for cls in CLOUD_SCL_CLASSES[1:]:
        is_cloud = is_cloud.Or(scl.eq(cls))
    if buffer_m and buffer_m > 0:
        is_cloud = is_cloud.focalMax(radius=buffer_m, units="meters",
                                     kernelType="circle").gt(0)
    return is_cloud.rename("cloud_mask")


def quality_stats(image: ee.Image, region: ee.Geometry) -> Dict[str, ee.Number]:
    scl = image.select("SCL")
    is_cloud = scl_cloud_mask(scl)
    pixel_area = ee.Image.pixelArea()

    valid_m2 = pixel_area.updateMask(scl.mask())           
    cloudy_m2 = pixel_area.updateMask(is_cloud.selfMask())

    sums = (
        valid_m2.rename("valid_m2")
        .addBands(cloudy_m2.rename("cloudy_m2"))
        .reduceRegion(
            reducer=ee.Reducer.sum(),
            geometry=region,
            scale=STATS_SCALE,
            bestEffort=True,
            tileScale=8,
            maxPixels=MAX_PIXELS,
        )
    )
    valid = ee.Number(sums.get("valid_m2", 0))
    cloudy = ee.Number(sums.get("cloudy_m2", 0))
    region_area = ee.Number(region.area(30)).max(1e-6)

    return {
        "cloud_pct": cloudy.divide(valid.max(1e-6)).multiply(100),
        "coverage_pct": valid.divide(region_area).multiply(100),
    }


def _annotate_scene(image: ee.Image, region: ee.Geometry, target_date: ee.Date) -> ee.Image:
    stats = quality_stats(image, region)
    sensing = ee.Date(image.get("system:time_start"))
    offset_days = sensing.difference(target_date, "day").abs()

    return image.set({
        "aoi_cloud_pct": stats["cloud_pct"],
        "aoi_coverage_pct": stats["coverage_pct"],
        "aoi_offset_days": offset_days,
        "aoi_score": stats["cloud_pct"].add(offset_days.multiply(DATE_WEIGHT_PCT_PER_DAY)),
        "sensing_date": sensing.format("YYYY-MM-dd"),
        "orbit_number": ee.Number(image.get("SENSING_ORBIT_NUMBER")).int(),
    })


def _candidate_collection(region: ee.Geometry, target_date: ee.Date,
                          window_days: int = SEARCH_WINDOW_DAYS) -> ee.ImageCollection:
    start = target_date.advance(-window_days, "day")
    end = target_date.advance(window_days + 1, "day")
    return (
        ee.ImageCollection(S2_COLLECTION_ID)
        .filterBounds(region)
        .filterDate(start, end)
        .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", MAX_GRANULE_CLOUD_PCT))
        .select(EXPORT_BANDS)
    )


def select_best_pass(region: ee.Geometry, target_date: ee.Date,
                     window_days: int = SEARCH_WINDOW_DAYS,
                     max_passes: int = MAX_PASSES_TO_TRY
                     ) -> Tuple[Optional[ee.Image], Optional[Dict[str, Any]]]:
    collection = _candidate_collection(region, target_date, window_days)
    total = collection.size().getInfo()
    logger.info("Кандидатов S2 в окне ±%s дн от %s: %s",
                window_days, target_date.format("YYYY-MM-dd").getInfo(), total)
    if not total:
        return None, None

    annotated = collection.map(lambda img: _annotate_scene(img, region, target_date))
    top = annotated.sort("aoi_score").limit(TOP_SCENES)

    dates = top.aggregate_array("sensing_date").getInfo()
    orbits = top.aggregate_array("orbit_number").getInfo()
    passes = list(dict.fromkeys(zip(dates, [int(o if o is not None else -1) for o in orbits])))

    for sensing_date, orbit in passes[:max_passes]:
        same_pass = annotated.filter(ee.Filter.And(
            ee.Filter.eq("sensing_date", sensing_date),
            ee.Filter.eq("orbit_number", orbit),
        ))
        first = ee.Image(same_pass.first())
        mosaic = same_pass.mosaic().copyProperties(first, first.propertyNames())
        n_tiles = same_pass.size().getInfo()

        q = ee.Dictionary(quality_stats(mosaic, region)).getInfo()
        logger.info("Пролёт %s (орбита %s, тайлов %s): облачность в AOI %.2f%%, "
                    "покрытие AOI %.2f%%", sensing_date, orbit, n_tiles,
                    q["cloud_pct"], q["coverage_pct"])

        if q["cloud_pct"] <= MAX_AOI_CLOUD_PCT and q["coverage_pct"] >= MIN_AOI_COVERAGE_PCT:
            meta = {
                "target_date": target_date.format("YYYY-MM-dd").getInfo(),
                "sensing_date": sensing_date,
                "orbit_number": orbit,
                "n_tiles": n_tiles,
                "aoi_cloud_pct": round(float(q["cloud_pct"]), 2),
                "aoi_coverage_pct": round(float(q["coverage_pct"]), 2),
                "spacecraft": first.get("SPACECRAFT_NAME").getInfo(),
                "scene_ids": same_pass.aggregate_array("system:index").getInfo(),
                "masked_scl_classes": list(CLOUD_SCL_CLASSES),
            }
            return mosaic, meta

    logger.warning("Ни один пролёт в окне ±%s дн не удовлетворяет порогу "
                   "(облачность в AOI <= %s%%, покрытие >= %s%%). "
                   "Мозаика из разных дат намеренно НЕ строится.",
                   window_days, MAX_AOI_CLOUD_PCT, MIN_AOI_COVERAGE_PCT)
    return None, None


def _export_band_order() -> List[str]:
    order = [b for b in (S2_BANDS_CONFIG.get("bands_order") or []) if b in EXPORT_BANDS]
    order += [b for b in EXPORT_BANDS if b not in order]
    return order


def prepare_for_export(image: ee.Image, crs: str,
                       scale: int = EXPORT_SCALE) -> ee.Image:
    scl = image.select("SCL").toUint8()
    good_pixel = scl_cloud_mask(scl).Not()

    spec = (
        image.select(REFLECTANCE_BANDS)
        .divide(10000.0)
        .toFloat()
        .updateMask(good_pixel)
        .resample("bilinear")
    )
    scl_band = scl.resample("nearest")

    out = spec.addBands(scl_band).select(_export_band_order())
    return out.setDefaultProjection(crs=crs, scale=scale)


def process_s2_image(image: ee.Image, crs: Optional[str] = None,
                     scale: int = EXPORT_SCALE) -> ee.Image:
    return prepare_for_export(image, crs or EXPORT_CRS, scale)


def validate_scl_values(image: ee.Image, region: ee.Geometry,
                        num_pixels: int = 300) -> None:
    try:
        values = (image.select("SCL")
                  .sample(region=region, scale=EXPORT_SCALE, numPixels=num_pixels)
                  .aggregate_array("SCL").getInfo())
        bad = sorted({v for v in values
                      if not float(v).is_integer() or not 0 <= int(v) <= SCL_MAX_CLASS})
        if bad:
            logger.error("SCL интерполирован! Некорректные значения: %s", bad[:20])
        else:
            logger.info("SCL OK: только целые классы 0..%s", SCL_MAX_CLASS)
    except Exception as exc:
        logger.warning("Не удалось валидировать SCL: %s", exc)


def _warn_if_too_large(region: ee.Geometry) -> None:
    try:
        area_m2 = float(region.area(30).getInfo())
        pixels = area_m2 / float(EXPORT_SCALE ** 2)
        est_mb = pixels * (4 * len(REFLECTANCE_BANDS) + 1) / 1e6
        if est_mb > 32:
            logger.info("Оценка GeoTIFF ~%.0f МБ. Используется тайловое скачивание, "
                        "ограничение getDownloadURL в 32 МБ обходится автоматически.", est_mb)
    except Exception as exc:
        logger.debug("Оценка объёма не удалась: %s", exc)


def _download_and_upload(image: ee.Image, prefix: str, region: ee.Geometry,
                         crs: str, meta: Dict[str, Any]) -> str:
    logger.info("S2 %s: дата пролёта %s (орбита %s, тайлов %s), облачность в AOI %s%%",
                prefix.upper(), meta["sensing_date"], meta["orbit_number"],
                meta["n_tiles"], meta["aoi_cloud_pct"])

    prepared = prepare_for_export(image, crs)
    if VALIDATE_SCL:
        validate_scl_values(prepared, region)

    _warn_if_too_large(region)

    download_params = {
        "crs": crs,
        "scale": EXPORT_SCALE,
        "fileFormat": "GeoTIFF",
        "maxPixels": MAX_PIXELS,
    }

    return tiled_download_and_upload(
        image=prepared,
        geometry=region,
        download_params=download_params,
        bucket_name=YC_BUCKET,
        conn_id=YANDEX_CONN_ID,
        folder_prefix=f"s2_{prefix}",
        file_extension=".tif",
        bands_config=S2_BANDS_CONFIG,
        target_crs=crs,
    )


def _export_for_date(target_date: ee.Date, prefix: str, region: ee.Geometry,
                     crs: str) -> Optional[Dict[str, Any]]:
    image, meta = select_best_pass(region, target_date)
    if image is None:
        return None
    try:
        path = _download_and_upload(image, prefix, region, crs, meta)
    except Exception as exc:
        logger.exception("Снимок S2 %s (%s) не обработан: %s",
                         prefix.upper(), meta["sensing_date"], exc)
        return None
    if not path:
        return None
    meta["path"] = path
    return meta


def parse_s2(id: Any = None,
             polygon: Any = None,
             date_pre: Any = None,
             date_peak: Any = None,
             **_ignored: Any) -> Dict[str, Any]:

    init_ee()

    aoi_id = id
    region = geojson_to_ee_geometry(polygon)
    
    crs = EXPORT_CRS
    logger.info("AOI=%s, CRS=%s, scale=%s м", aoi_id, crs, EXPORT_SCALE)

    result: Dict[str, Any] = {
        "pre": None,
        "peak": None,
        "meta": {"id": aoi_id, "crs": crs, "scale": EXPORT_SCALE,
                 "masked_scl_classes": list(CLOUD_SCL_CLASSES), "scenes": {}},
    }

    for prefix, raw_date in (("pre", date_pre), ("peak", date_peak)):
        if not raw_date:
            logger.error("Не задана дата для %s", prefix)
            continue
        try:
            target_date = _parse_date(raw_date, prefix)
        except ValueError as exc:
            logger.error("%s", exc)
            continue

        scene_meta = _export_for_date(target_date, prefix, region, crs)
        result["meta"]["scenes"][prefix] = scene_meta
        result[prefix] = scene_meta["path"] if scene_meta else None

    if not result["pre"] and not result["peak"]:
        raise RuntimeError(f"Нет пригодных снимков S2 для AOI={aoi_id} "
                           f"(date_pre={date_pre}, date_peak={date_peak})")
    return result