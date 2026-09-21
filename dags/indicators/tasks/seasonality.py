import rasterio
import os
import matplotlib.pyplot as plt
import numpy as np

from utils.gee_storage import download_file, upload_file_to_yandex

YC_BUCKET = os.getenv("YC_BUCKET")
YANDEX_CONN_ID = os.getenv("YANDEX_CONN_ID")

def calc_seasonality(url):
    original_filename = url.split('/')[-1]
    metaname = ''.join(original_filename.split('_')[1:])
    local_input_path = f"/tmp/{original_filename}"
    download_url= f"https://storage.yandexcloud.net/{YC_BUCKET}/{url}"
    file = download_file(url=download_url, local_path=local_input_path)
    
    with rasterio.open(file) as src:
        
        profile = src.profile
    
        seasonality = src.read(7).astype(np.float32)
        
        if src.nodata is not None:
            seasonality[seasonality == src.nodata] = np.nan
        
        profile.update(dtype=rasterio.float32, count=1, nodata=np.nan)
        with rasterio.open(os.path.join('/tmp', 'GSW_SEASONALITY.tif'), 'w', **profile) as dst:
            dst.write(seasonality.astype(np.float32), 1)
        
        
        result = upload_file_to_yandex(
        local_path='/tmp/GSW_SEASONALITY.tif',
        yandex_object_name=f'gee_exports/seasonality/seasonality_{metaname}', 
        bucket_name=YC_BUCKET,
        conn_id=YANDEX_CONN_ID,)
        
        return result
        