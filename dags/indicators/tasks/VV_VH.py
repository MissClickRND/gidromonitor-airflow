import rasterio
import os
import matplotlib.pyplot as plt
import numpy as np

from utils.gee_storage import download_file, upload_file_to_yandex

YC_BUCKET = os.getenv("YC_BUCKET")
YANDEX_CONN_ID = os.getenv("YANDEX_CONN_ID")


def calc_vv_vh(url):
    original_filename = url.split('/')[-1]
    foldername = url.split('/')[-2]
    metaname = ''.join(original_filename.split('_')[1:])
    local_input_path = f"/tmp/{original_filename}"
    download_url= f"https://storage.yandexcloud.net/{YC_BUCKET}/{url}"
    file = download_file(url=download_url, local_path=local_input_path)
    with rasterio.open(file) as src:
        
        profile = src.profile
        
        vv_db = src.read(1).astype(np.float32)
        vh_db = src.read(2).astype(np.float32)
        
        ratio_db = vv_db - vh_db
        
        profile.update(dtype=rasterio.float32, count=1, nodata=np.nan)
        with rasterio.open(os.path.join('/tmp', 'S1_VV_VH_dB.tif'), 'w', **profile) as dst:
            dst.write(ratio_db.astype(np.float32), 1)    
        
        result = upload_file_to_yandex(
            local_path='/tmp/S1_VV_VH_dB.tif',
            yandex_object_name=f'gee_exports/{foldername}/vv_vh_{metaname}', 
            bucket_name=YC_BUCKET,
            conn_id=YANDEX_CONN_ID,)
                
        return result