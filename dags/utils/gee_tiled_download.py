import os
import math
import tempfile
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List, Tuple

import numpy as np
import rasterio
from rasterio.merge import merge as rasterio_merge
from rasterio.mask import mask as rasterio_mask
from rasterio.warp import (
    calculate_default_transform,
    reproject,
    transform_geom,
    Resampling,
)

import ee

from utils.gee_storage import download_file, upload_file_to_yandex
from utils.file_utils import process_downloaded_file

log = logging.getLogger(__name__)


def _get_geometry_bounds_deg(
    geometry: ee.Geometry,
) -> Tuple[float, float, float, float]:
    coords = geometry.bounds().coordinates().getInfo()
    ring = coords[0]
    lons = [c[0] for c in ring]
    lats = [c[1] for c in ring]
    return min(lons), min(lats), max(lons), max(lats)


def _build_tile_grid(
    bounds: Tuple[float, float, float, float],
    tile_size_deg: float,
) -> List[Tuple[float, float, float, float]]:
    min_lon, min_lat, max_lon, max_lat = bounds
    cols = max(1, math.ceil((max_lon - min_lon) / tile_size_deg))
    rows = max(1, math.ceil((max_lat - min_lat) / tile_size_deg))

    tiles = []
    for r in range(rows):
        for c in range(cols):
            t_min_lon = min_lon + c * tile_size_deg
            t_min_lat = min_lat + r * tile_size_deg
            t_max_lon = min(t_min_lon + tile_size_deg, max_lon)
            t_max_lat = min(t_min_lat + tile_size_deg, max_lat)
            tiles.append((t_min_lon, t_min_lat, t_max_lon, t_max_lat))
    return tiles


def _tile_to_ee_geometry(
    tile_bounds: Tuple[float, float, float, float],
) -> ee.Geometry:
    min_lon, min_lat, max_lon, max_lat = tile_bounds
    return ee.Geometry.Rectangle(
        [min_lon, min_lat, max_lon, max_lat],
        proj="EPSG:4326",
        geodesic=False,
    )


def _filter_tiles_by_intersection(
    tiles: List[Tuple[float, float, float, float]],
    geometry: ee.Geometry,
) -> List[Tuple[float, float, float, float]]:
    if len(tiles) <= 1:
        return tiles

    ee_tiles = [_tile_to_ee_geometry(t) for t in tiles]

    try:
        intersects_list = [geometry.intersects(t, maxError=1) for t in ee_tiles]
        results = ee.List(intersects_list).getInfo()
        filtered = [tb for tb, hit in zip(tiles, results) if hit]

        if not filtered:
            log.warning("Фильтрация не оставила ни одного тайла. Скачиваю всю сетку.")
            return tiles

        log.info(f"Тайлов после фильтрации: {len(filtered)} / {len(tiles)}")
        return filtered

    except ee.EEException as e:
        log.warning(f"GEE intersects failed: {e}. Скачиваю всю сетку.")
        return tiles
    except Exception as e:
        log.warning(f"Ошибка фильтрации тайлов: {e}. Скачиваю всю сетку.")
        return tiles


def _download_single_tile(
    image: ee.Image,
    tile_geom: ee.Geometry,
    download_params: Dict[str, Any],
    local_path: str,
    timeout: int = 600,
) -> Optional[str]:
    params = {**download_params, "region": tile_geom}

    try:
        url = image.getDownloadURL(params)
    except ee.EEException as e:
        log.warning(f"Не удалось получить URL для тайла: {e}")
        return None

    try:
        download_file(url, local_path, timeout=timeout)
    except Exception as e:
        log.warning(f"Ошибка скачивания тайла {local_path}: {e}")
        if os.path.exists(local_path):
            os.remove(local_path)
        return None

    if os.path.getsize(local_path) == 0:
        log.warning(f"Пустой файл тайла: {local_path}")
        os.remove(local_path)
        return None

    return local_path



def _reproject_raster(src_path: str, target_crs: str) -> None:
    with rasterio.open(src_path) as src:
        src_crs_str = src.crs.to_string() if src.crs else None

        if src_crs_str == target_crs:
            log.info(f"Растр уже в {target_crs}, репроекция не требуется")
            return

        log.info(f"Репроецирую растр из {src_crs_str} в {target_crs}...")

        transform, width, height = calculate_default_transform(
            src.crs, target_crs, src.width, src.height, *src.bounds
        )
        profile = src.profile.copy()
        profile.update(
            crs=target_crs,
            transform=transform,
            width=width,
            height=height,
        )

        tmp = src_path + ".reproj_tmp.tif"
        with rasterio.open(tmp, "w", **profile) as dst:
            for i in range(1, src.count + 1):
                reproject(
                    source=rasterio.band(src, i),
                    destination=rasterio.band(dst, i),
                    src_transform=src.transform,
                    src_crs=src.crs,
                    dst_transform=transform,
                    dst_crs=target_crs,
                    resampling=Resampling.bilinear,
                    num_threads=4,
                )

    os.replace(tmp, src_path)
    log.info(f"Репроекция завершена → {target_crs}")



def _clip_to_geometry(tif_path: str, geojson_geom: Dict) -> None:
    with rasterio.open(tif_path) as src:
        raster_crs = src.crs.to_string()
        geom_src_crs = "EPSG:4326"

        if raster_crs != geom_src_crs:
            try:
                geojson_geom = transform_geom(
                    src_crs=geom_src_crs,
                    dst_crs=raster_crs,
                    geom=geojson_geom,
                    precision=-1,
                )
            except Exception as e:
                log.warning(f"Не удалось репроецировать геометрию: {e}. Пропускаю обрезку.")
                return

        try:
            out_image, out_transform = rasterio_mask(
                src, [geojson_geom], crop=True, nodata=np.nan,
            )
        except Exception as e:
            log.warning(f"Не удалось обрезать растр: {e}. Оставляю полный мозаичный растр.")
            return

        profile = src.profile.copy()

    profile.update(
        height=out_image.shape[1],
        width=out_image.shape[2],
        transform=out_transform,
        nodata=np.nan,
    )

    tmp = tif_path + ".clip_tmp.tif"
    with rasterio.open(tmp, "w", **profile) as dst:
        dst.write(out_image)

    os.replace(tmp, tif_path)
    log.info("Растр обрезан по исходной геометрии")


def _merge_tiles(
    tile_paths: List[str],
    output_path: str,
    original_geometry_geojson: Optional[Dict] = None,
    target_crs: Optional[str] = None,
) -> str:
    src_datasets = [rasterio.open(p) for p in tile_paths]

    try:
        mosaic, mosaic_transform = rasterio_merge(src_datasets)

        profile = src_datasets[0].profile.copy()
        profile.update(
            driver="GTiff",
            height=mosaic.shape[1],
            width=mosaic.shape[2],
            count=mosaic.shape[0],
            transform=mosaic_transform,
            compress="deflate",
            predictor=2,
            tiled=True,
            blockxsize=512,
            blockysize=512,
            BIGTIFF="IF_SAFER",
        )

        with rasterio.open(output_path, "w", **profile) as dst:
            dst.write(mosaic)

        log.info(
            f"Склейка: {output_path}  "
            f"({mosaic.shape[2]}×{mosaic.shape[1]}, {mosaic.shape[0]} band(s))"
        )


        if target_crs is not None:
            _reproject_raster(output_path, target_crs)
            
        if original_geometry_geojson is not None:
            _clip_to_geometry(output_path, original_geometry_geojson)

        return output_path

    finally:
        for ds in src_datasets:
            ds.close()


def tiled_download_and_upload(
    image: ee.Image,
    geometry: ee.Geometry,
    download_params: Dict[str, Any],
    bucket_name: str,
    conn_id: str,
    folder_prefix: str,
    tile_size_deg: float = 0.25,
    file_extension: str = ".tif",
    timeout: int = 600,
    bands_config: Optional[Dict[str, Any]] = None,
    clip_to_original: bool = True,
    target_crs: str = "EPSG:32652",
) -> str:
    params = {k: v for k, v in download_params.items() if k != "region"}

    merged_path: Optional[str] = None
    tile_paths: List[str] = []
    clip_geojson: Optional[Dict] = None

    try:
        bounds = _get_geometry_bounds_deg(geometry)
        log.info(f"Bounding box: {bounds}")

        tiles = _build_tile_grid(bounds, tile_size_deg)
        log.info(f"Сетка: {len(tiles)} тайлов (tile_size={tile_size_deg}°)")

        tiles = _filter_tiles_by_intersection(tiles, geometry)
        if not tiles:
            raise ValueError("Ни один тайл не пересекается с геометрией")

        if clip_to_original:
            clip_geojson = geometry.getInfo()

        tmp_dir = tempfile.gettempdir()
        ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        
        remote_prefix = folder_prefix.strip("/")
        file_base_name = os.path.basename(remote_prefix).lower()

        for idx, tile_bounds in enumerate(tiles):
            tile_geom = _tile_to_ee_geometry(tile_bounds)
            tile_file = os.path.join(
                tmp_dir, f"tile_{idx:04d}_{os.getpid()}{file_extension}"
            )

            log.info(
                f"Тайл {idx + 1}/{len(tiles)}: "
                f"lon=[{tile_bounds[0]:.4f}..{tile_bounds[2]:.4f}], "
                f"lat=[{tile_bounds[1]:.4f}..{tile_bounds[3]:.4f}]"
            )

            path = _download_single_tile(
                image=image,
                tile_geom=tile_geom,
                download_params=params,
                local_path=tile_file,
                timeout=timeout,
            )

            if path is None:
                log.warning("пропущен")
                continue

            if bands_config is not None:
                processed, _ = process_downloaded_file(path, bands_config=bands_config)
                if processed != path and os.path.exists(path):
                    os.remove(path)
                path = processed

            tile_paths.append(path)
            log.info(f"скачан ({os.path.getsize(path):,} байт)")

        if not tile_paths:
            raise RuntimeError("Не удалось скачать ни одного тайла")

        log.info(f"Скачано тайлов: {len(tile_paths)} / {len(tiles)}")


        merged_name = f"{file_base_name}_{ts}{file_extension}"
        
        merged_path = os.path.join(tmp_dir, merged_name)

        _merge_tiles(
            tile_paths=tile_paths,
            output_path=merged_path,
            original_geometry_geojson=clip_geojson,
            target_crs=target_crs,
        )

        s3_key = f"gee_exports/{remote_prefix}/{merged_name}"
        
        upload_file_to_yandex(
            local_path=merged_path,
            bucket_name=bucket_name,
            yandex_object_name=s3_key,
            conn_id=conn_id,
        )

        return s3_key

    except Exception:
        log.exception("Ошибка в tiled_download_and_upload")
        raise

    finally:
        all_tmp = list(tile_paths)
        if merged_path and merged_path not in all_tmp:
            all_tmp.append(merged_path)

        for p in all_tmp:
            if p and os.path.exists(p):
                try:
                    os.remove(p)
                    log.info(f"Удалён временный файл: {p}")
                except OSError as e:
                    log.warning(f"Не удалось удалить {p}: {e}")