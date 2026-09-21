import os
import tempfile
from datetime import datetime
from typing import Optional, Dict, List
import numpy as np
import rasterio

from airflow.utils.log.logging_mixin import LoggingMixin

from utils.gee_storage import upload_file_to_yandex, download_file_from_yandex

log = LoggingMixin().log

def merge_layers_to_geotiff(
    layers_dict: Dict[str, str],
    bucket_name: str,
    conn_id: str,
    folder_prefix: str = "merged",
    file_extension: str = ".tif",
) -> str:

    log.info(f"Начинаю объединение {len(layers_dict)} слоев в единый GeoTIFF...")

    tmp_dir = tempfile.gettempdir()
    downloaded_local_paths: List[str] = []
    merged_local_path: Optional[str] = None

    try:
        for layer_name, s3_key in layers_dict.items():
            if not s3_key:
                log.warning(f"Слой '{layer_name}' пропущен: передан пустой путь.")
                continue

            local_path = os.path.join(tmp_dir, f"temp_{layer_name}_{os.getpid()}.tif")
            
            # Используем единую функцию скачивания из облака
            download_file_from_yandex(
                bucket_name=bucket_name,
                s3_key=s3_key,
                local_path=local_path,
                conn_id=conn_id
            )
            downloaded_local_paths.append((layer_name, local_path))
            log.info(f"Слой '{layer_name}' успешно скачан.")

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

        log.info(f"Объединение завершено. Итоговый файл: {result_s3_key}")
        return result_s3_key

    except Exception as e:
        log.error(f"Ошибка при объединении слоев: {e}")
        raise

    finally:
        paths_to_cleanup = [path for _, path in downloaded_local_paths]
        if merged_local_path and merged_local_path not in paths_to_cleanup:
            paths_to_cleanup.append(merged_local_path)

        for path in paths_to_cleanup:
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                    log.info(f"Очищен временный файл: {path}")
                except Exception as cleanup_error:
                    log.warning(f"Не удалось удалить {path}: {cleanup_error}")