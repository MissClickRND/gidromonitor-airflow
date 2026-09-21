import os
import tempfile
import requests
from datetime import datetime
from typing import Optional, Dict, List, Any

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.warp import calculate_default_transform, reproject, Resampling

from airflow.utils.log.logging_mixin import LoggingMixin
from airflow.providers.amazon.aws.hooks.s3 import S3Hook

from utils.file_utils import process_downloaded_file

log = LoggingMixin().log

YC_BUCKET = os.getenv("YC_BUCKET")
YANDEX_CONN_ID = os.getenv("YANDEX_CONN_ID")

def download_file(url: str, local_path: str, timeout: int = 600) -> str:
    log.info(f"Начинаю скачивание: {url}")
    
    with requests.get(url, stream=True, timeout=timeout) as response:
        response.raise_for_status()
        
        content_type = response.headers.get('Content-Type', '')
        log.info(f"Content-Type ответа: {content_type}")
        
        if 'application/json' in content_type.lower():
            raise RuntimeError(
                f"Сервер вернул JSON вместо файла: {response.text[:500]}"
            )
        
        log.info(f"Скачиваю файл во временную директорию: {local_path}")
        
        with open(local_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    f.write(chunk)
    
    file_size = os.path.getsize(local_path)
    log.info(f"Скачивание завершено. Размер: {file_size:,} байт")
    return local_path


def upload_file_to_yandex(
    local_path: str,
    bucket_name: str,
    yandex_object_name: str,
    conn_id: str,
) -> str:
    log.info(f"Загружаю в Yandex Object Storage: s3://{bucket_name}/{yandex_object_name}")
    
    s3_hook = S3Hook(aws_conn_id=conn_id)
    s3_hook.load_file(
        filename=local_path,
        key=yandex_object_name,
        bucket_name=bucket_name,
        replace=True,
    )
    
    log.info(f"Успешно загружено: {yandex_object_name}")
    return yandex_object_name


def download_and_upload_to_yandex(
    url: str,
    bucket_name: str,
    conn_id: str,
    folder_prefix: str,
    file_extension: str = ".tif",
    timeout: int = 600,
    bands_config: Optional[Dict[str, Any]] = None,
) -> str:
    ts = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
    clean_prefix = folder_prefix.strip('/').lower()
    file_name = f"{clean_prefix}_{ts}{file_extension}"
    
    tmp_dir = tempfile.gettempdir()
    local_path = os.path.join(tmp_dir, file_name)
    
    yandex_object_name = f"gee_exports/{clean_prefix}/{file_name}"
    
    upload_path = None
    stacked_path = None
    
    try:
        download_file(url, local_path, timeout)
        
        if bands_config is not None:
            upload_path, file_type = process_downloaded_file(
                local_path,
                bands_config=bands_config,
            )
            
            if file_type == 'zip_converted':
                stacked_path = upload_path
                log.info("ZIP-архив преобразован в многослойный GeoTIFF")
        else:
            upload_path = local_path
        
        result = upload_file_to_yandex(
            local_path=upload_path,
            bucket_name=bucket_name,
            yandex_object_name=yandex_object_name,
            conn_id=conn_id,
        )
        
        return result
        
    except Exception as e:
        log.error(f"Ошибка при обработке файла: {e}")
        raise
    
    finally:
        paths_to_cleanup = [local_path]
        if stacked_path and stacked_path != local_path:
            paths_to_cleanup.append(stacked_path)
        
        for path in paths_to_cleanup:
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                    log.info(f"Очищен временный файл: {path}")
                except Exception as cleanup_error:
                    log.warning(f"Не удалось удалить {path}: {cleanup_error}")



def merge_layers_to_geotiff(
    layers_dict: Dict[str, str],
    bucket_name: str,
    conn_id: str,
    folder_prefix: str = "merged",
    file_extension: str = ".tif",
    create_cog: bool = True,
    timeout: int = 600,
) -> str:

    log.info(f"Начинаю объединение {len(layers_dict)} слоев в единый GeoTIFF...")

    tmp_dir = tempfile.gettempdir()
    downloaded_local_paths: List[tuple] = []
    merged_local_path: Optional[str] = None
    cog_local_path: Optional[str] = None

    try:
        for layer_name, url in layers_dict.items():
            if not url:
                log.warning(f"Слой '{layer_name}' пропущен: передан пустой URL.")
                continue

            local_path = os.path.join(tmp_dir, f"temp_{layer_name}_{os.getpid()}.tif")
            
            download_url = f"https://storage.yandexcloud.net/{YC_BUCKET}/{url}"
            
            download_file(url=download_url, local_path=local_path, timeout=timeout)
            
            downloaded_local_paths.append((layer_name, local_path))
            log.info(f"Слой '{layer_name}' успешно скачан по URL.")

        if not downloaded_local_paths:
            raise ValueError("Нет ни одного валидного файла для объединения.")

        base_layer_name, base_path = downloaded_local_paths[0]
        with rasterio.open(base_path) as src:
            profile = src.profile.copy()
            base_transform = src.transform
            base_crs = src.crs
            base_shape = src.shape

        num_bands = len(downloaded_local_paths)
        profile.update(
            driver='GTiff',
            count=num_bands,
            dtype='float32',
            compress='deflate',
            predictor=2,
            tiled=True,
            nodata=np.nan
        )

        ts = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        clean_prefix = folder_prefix.strip('/').lower()
        merged_filename = f"{clean_prefix}_{ts}{file_extension}"
        merged_local_path = os.path.join(tmp_dir, merged_filename)

        log.info(f"Создаю объединенный файл {merged_filename} с {num_bands} бэндами...")

        with rasterio.open(merged_local_path, 'w', **profile) as dst:
            for i, (layer_name, file_path) in enumerate(downloaded_local_paths, start=1):
                with rasterio.open(file_path) as src:
                    if src.transform != base_transform or src.shape != base_shape:
                        raise ValueError(
                            f"Слой '{layer_name}' не совпадает по геометрии с базовым слоем '{base_layer_name}'. "
                            f"Убедитесь, что все файлы имеют одинаковые scale и region."
                        )

                    data = src.read(1).astype('float32')
                    dst.write(data, i)
                    dst.set_band_description(i, layer_name)
                    log.info(f"  Добавлен бэнд {i}: {layer_name}")

        result_s3_key = f"gee_exports/{clean_prefix}/{merged_filename}"
        log.info(f"Загружаю итоговый файл в s3://{bucket_name}/{result_s3_key}")

        upload_file_to_yandex(
            local_path=merged_local_path,
            bucket_name=bucket_name,
            yandex_object_name=result_s3_key,
            conn_id=conn_id,
        )
        
        if create_cog:
            cog_filename = f"{clean_prefix}_{ts}_cog.tif"
            cog_local_path = os.path.join(tmp_dir, cog_filename)
            cog_s3_key = f"gee_exports/{clean_prefix}/{cog_filename}"
            
            log.info(f"Создаю Cloud Optimized GeoTIFF в EPSG:3857: {cog_filename}")
            
            target_crs = "EPSG:3857"
            
            with rasterio.open(merged_local_path) as src:
                transform, width, height = calculate_default_transform(
                    src.crs, target_crs, src.width, src.height, *src.bounds
                )
                
                cog_profile = src.profile.copy()
                cog_profile.update(
                    crs=target_crs,
                    transform=transform,
                    width=width,
                    height=height,
                    driver='GTiff',
                    tiled=True,
                    blockxsize=512,
                    blockysize=512,
                    compress='deflate',
                    predictor=2,
                    interleave='band',
                    BIGTIFF='IF_SAFER'
                )
                
                with rasterio.open(cog_local_path, 'w', **cog_profile) as dst:
                    for i in range(1, src.count + 1):
                        resampling_method = Resampling.bilinear 
                        
                        reproject(
                            source=rasterio.band(src, i),
                            destination=rasterio.band(dst, i),
                            src_transform=src.transform,
                            src_crs=src.crs,
                            dst_transform=transform,
                            dst_crs=target_crs,
                            resampling=resampling_method,
                            num_threads=4
                        )
                        
                        if src.descriptions[i-1]:
                            dst.set_band_description(i, src.descriptions[i-1])
                            
            with rasterio.open(cog_local_path, 'r+') as dst:
                overviews = []
                min_dim = min(dst.width, dst.height)
                level = 1
                while min_dim // (2 ** level) >= 256:
                    overviews.append(2 ** level)
                    level += 1
                
                if overviews:
                    dst.build_overviews(overviews, Resampling.nearest)
                    dst.update_tags(ns='rio_overview', resampling='nearest')
                    log.info(f"Добавлены overviews для COG: {overviews}")
                else:
                    log.warning("Изображение слишком маленькое для создания overviews.")
            
            log.info(f"Загружаю COG файл (EPSG:3857) в s3://{bucket_name}/{cog_s3_key}")
            upload_file_to_yandex(
                local_path=cog_local_path,
                bucket_name=bucket_name,
                yandex_object_name=cog_s3_key,
                conn_id=conn_id,
            )
            
            log.info(f"COG файл успешно создан и загружен: {cog_s3_key}")

    except Exception as e:
        log.error(f"Ошибка при объединении слоев: {e}")
        raise

    finally:
        paths_to_cleanup = [path for _, path in downloaded_local_paths]
        if merged_local_path and merged_local_path not in paths_to_cleanup:
            paths_to_cleanup.append(merged_local_path)
        if cog_local_path and cog_local_path not in paths_to_cleanup:
            paths_to_cleanup.append(cog_local_path)

        for path in paths_to_cleanup:
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                    log.info(f"Очищен временный файл: {path}")
                except Exception as cleanup_error:
                    log.warning(f"Не удалось удалить {path}: {cleanup_error}")