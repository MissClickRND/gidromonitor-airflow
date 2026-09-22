import rasterio
import os
import matplotlib.pyplot as plt
import numpy as np

from utils.gee_storage import download_file, upload_file_to_yandex

YC_BUCKET = os.getenv("YC_BUCKET")
YANDEX_CONN_ID = os.getenv("YANDEX_CONN_ID")

def calc_buildup(url):
    original_filename = url.split('/')[-1]
    foldername = url.split('/')[-2]
    metaname = ''.join(original_filename.split('_')[1:])
    
    local_input_path = f"/tmp/{original_filename}"
    download_url= f"https://storage.yandexcloud.net/{YC_BUCKET}/{url}"
    file = download_file(url=download_url, local_path=local_input_path)
    
    with rasterio.open(file) as src:
        
        profile = src.profile
    
        buildup = src.read(1).astype(np.float32)
        
        if src.nodata is not None:
            buildup[buildup == src.nodata] = np.nan
            
        buildup[buildup < 0] = 0.0
        
        
        profile.update(dtype=rasterio.float32, count=1, nodata=np.nan)
        with rasterio.open(os.path.join('/tmp', 'ESA_BUILDUP.tif'), 'w', **profile) as dst:
            dst.write(buildup.astype(np.float32), 1)
        
        
        result = upload_file_to_yandex(
        local_path='/tmp/ESA_BUILDUP.tif',
        yandex_object_name=f'gee_exports/{foldername}/buildup_{metaname}', 
        bucket_name=YC_BUCKET,
        conn_id=YANDEX_CONN_ID,)
        
        return result
        