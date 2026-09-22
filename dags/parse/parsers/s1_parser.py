import json
import os
import logging
from datetime import datetime, timezone

import ee

from utils.file_utils import S1_BANDS_CONFIG
from utils.geojson_utils import geojson_to_ee_geometry
from utils.gee_tiled_download import tiled_download_and_upload

log = logging.getLogger(__name__)

GEE_PROJECT = os.getenv("GEE_PROJECT")
GEE_KEY_PATH = os.getenv("GEE_KEY_PATH")
YC_BUCKET = os.getenv("YC_BUCKET")
YANDEX_CONN_ID = os.getenv("YANDEX_CONN_ID")

S1_COLLECTION    = "COPERNICUS/S1_GRD"
S1_BANDS         = ["VV", "VH", "angle"]

TARGET_CRS       = "EPSG:32652"
SCALE            = 10
TOLERANCE_DAYS   = 4 
SPECKLE_RADIUS_M = 30
EDGE_ERODE_PX    = 2
ANGLE_RANGE      = (1.0, 60.0)
MAX_PIXELS       = 500_000_000

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

def _epoch_ms(date_str: str) -> float:
    dt = datetime.fromisoformat(str(date_str).replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp() * 1000

def _valid_mask(src: ee.Image) -> ee.Image:
    angle = src.select("angle")
    native = src.select(S1_BANDS).mask().reduce(ee.Reducer.min())

    valid = (
        angle.gt(ANGLE_RANGE[0])
        .And(angle.lt(ANGLE_RANGE[1]))
        .And(native)
    )
    return valid.focal_min(EDGE_ERODE_PX, "circle", "pixels")

def _prepare(image_id: str, geometry: ee.Geometry) -> ee.Image:
    src = ee.Image(image_id)

    valid = _valid_mask(src)

    db = src.select(S1_BANDS).updateMask(valid)
    power = db.divide(10).exp10()

    filtered = power.focal_median(SPECKLE_RADIUS_M, "circle", "meters")

    out = filtered.log10().multiply(10).clamp(-50, 10).float().rename(S1_BANDS)
    return out.updateMask(valid).clip(geometry)

def _candidates(geometry: ee.Geometry, start_ms: float, end_ms: float):
    coll = (
        ee.ImageCollection(S1_COLLECTION)
        .filterBounds(geometry)
        .filterDate(int(start_ms), int(end_ms))
        .filter(ee.Filter.eq("instrumentMode", "IW"))
        .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VV"))
        .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VH"))
    )

    props = [
        "system:time_start",
        "orbitProperties_pass",
        "relativeOrbitNumber_start",
        "system:index",
    ]
    raw = (
        coll.reduceColumns(ee.Reducer.toList(len(props)), props)
            .getInfo()
            .get("list", [])
    )
    if not raw:
        return []

    rows = list(zip(*raw))
    return [
        {
            "time": float(r[0]),
            "pass": r[1],
            "rel": int(r[2]),
            "id": f"{S1_COLLECTION}/{r[3]}",
        }
        for r in rows
    ]

def _pick_pair(candidates, targets, tol_ms):
    groups = {}
    for c in candidates:
        groups.setdefault((c["pass"], c["rel"]), []).append(c)

    best = None
    for key, items in groups.items():
        chosen = {}
        total_dt = 0.0
        ok = True

        for label, t in targets.items():
            near = [c for c in items if abs(c["time"] - t) <= tol_ms]
            if not near:
                ok = False
                break
            c = min(near, key=lambda x: abs(x["time"] - t))
            chosen[label] = c
            total_dt += abs(c["time"] - t)

        if not ok:
            continue
        if len({c["id"] for c in chosen.values()}) < len(targets):
            continue

        score = (total_dt, -len(items))
        if best is None or score < best[0]:
            best = (score, chosen)

    if best is None:
        raise RuntimeError("Не найдена согласованная пара снимков по орбите")
    return best[1]

def parse_s1(id: str, polygon, date_pre: str, date_peak: str, **_):
    init_ee()

    bucket = os.environ["YC_BUCKET"]
    conn_id = os.environ["YANDEX_CONN_ID"]

    geometry = geojson_to_ee_geometry(polygon)

    targets = {
        "before": _epoch_ms(date_pre),
        "after": _epoch_ms(date_peak),
    }
    tol_ms = TOLERANCE_DAYS * 86_400_000
    start_ms = min(targets.values()) - tol_ms
    end_ms = max(targets.values()) + tol_ms

    candidates = _candidates(geometry, start_ms, end_ms)
    if not candidates:
        raise RuntimeError("Нет данных S1 в заданном окне")

    chosen = _pick_pair(candidates, targets, tol_ms)

    download_params = {
        "crs": TARGET_CRS,
        "scale": SCALE,
        "fileFormat": "GeoTIFF",
        "maxPixels": MAX_PIXELS,
    }

    result = {}
    for label in ("before", "after"):
        cand = chosen[label]
        image = _prepare(cand["id"], geometry)

        result[label] = tiled_download_and_upload(
            image=image,
            geometry=geometry,
            download_params=download_params,
            bucket_name=bucket,
            conn_id=conn_id,
            folder_prefix=f"{id}/s1_{label}",
            file_extension=".tif",
            bands_config=S1_BANDS_CONFIG,
            target_crs=TARGET_CRS,
        )

    return result