"""
Модуль для работы с хранилищами: скачивание из GEE и загрузка в Yandex Cloud.
Поддерживает автоматическую обработку ZIP-архивов от GEE.
"""
import os
import requests
import tempfile
from datetime import datetime
from typing import Optional, Dict, Any

from airflow.providers.amazon.aws.hooks.s3 import S3Hook
from airflow.utils.log.logging_mixin import LoggingMixin

from utils.file_utils import process_downloaded_file

log = LoggingMixin().log


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
        log.error(f"❌ Ошибка при обработке файла: {e}")
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