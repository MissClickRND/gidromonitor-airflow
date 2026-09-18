import os
import requests
from datetime import datetime
from airflow.providers.amazon.aws.hooks.s3 import S3Hook
from airflow.utils.log.logging_mixin import LoggingMixin

log = LoggingMixin().log

def download_and_upload_to_yandex(
    url: str, 
    bucket_name: str, 
    conn_id: str, 
    folder_prefix: str, 
    file_extension: str = ".tif",
    timeout: int = 600
) -> str:
    ts = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
    
    clean_prefix = folder_prefix.strip('/').lower()
    file_name = f"{clean_prefix}_{ts}{file_extension}"
    local_path = f"/tmp/{file_name}"
    
    yandex_object_name = f"gee_exports/{clean_prefix}/{file_name}"

    try:
        log.info(f"Начинаю скачивание: {url}")
        with requests.get(url, stream=True, timeout=timeout) as response:
            response.raise_for_status()
            
            content_type = response.headers.get('Content-Type', '')
            if 'application/json' in content_type.lower():
                raise RuntimeError(f"Earth Engine вернул ошибку вместо файла: {response.text[:500]}")

            log.info(f"Скачиваю файл во временную директорию: {local_path}")
            with open(local_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=1024 * 1024): # 1 MB chunks
                    if chunk:
                        f.write(chunk)
        
        log.info(f"Скачивание завершено. Загружаю в Yandex Object Storage: s3://{bucket_name}/{yandex_object_name}")
        s3_hook = S3Hook(aws_conn_id=conn_id)
        s3_hook.load_file(
            filename=local_path,
            key=yandex_object_name,
            bucket_name=bucket_name,
            replace=True
        )
        
        log.info(f"Успешно загружено: {yandex_object_name}")
        return yandex_object_name

    except Exception as e:
        log.error(f"Ошибка при обработке файла: {e}")
        raise

    finally:
        if os.path.exists(local_path):
            log.info(f"Очищаю временный файл: {local_path}")
            os.remove(local_path)