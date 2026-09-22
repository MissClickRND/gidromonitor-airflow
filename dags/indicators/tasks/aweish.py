import rasterio
import os
import matplotlib.pyplot as plt
import numpy as np

from utils.gee_storage import download_file, upload_file_to_yandex

YC_BUCKET = os.getenv("YC_BUCKET")
YANDEX_CONN_ID = os.getenv("YANDEX_CONN_ID")

def calc_aweish(url='gee_exports/s2_before/s2_before_20260920_162354.tif'):
    original_filename = url.split('/')[-1]
    foldername = url.split('/')[-2]
    metaname = ''.join(original_filename.split('_')[1:])
    local_input_path = f"/tmp/{original_filename}"
    download_url= f"https://storage.yandexcloud.net/{YC_BUCKET}/{url}"
    file = download_file(url=download_url, local_path=local_input_path)
    with rasterio.open(file) as src:
        
        profile = src.profile
        
        blue = src.read(1).astype(np.float32)# B2 - синий
        green = src.read(2).astype(np.float32)  # B3 - зеленый
        red = src.read(3).astype(np.float32)  # B4 - красный
        nir = src.read(4).astype(np.float32)  # B8 - ближний ИК
        swir1 = src.read(5).astype(np.float32)  # B11 - Swir 1
        swir2 = src.read(6).astype(np.float32)  # B12 - Swir 2
        scl = src.read(7).astype(np.float32) * 10000.0  # SCL - Маска
        
        aweish = (blue + 2.5 * green - 1.5 * (nir + swir1) - 0.25 * swir2)
        
        
        cloud_shadow_mask = np.isin(scl, [3, 8, 9, 10])
        aweish[cloud_shadow_mask] = np.nan
        
        profile.update(dtype=rasterio.float32, count=1, nodata=np.nan)
        with rasterio.open(os.path.join('/tmp', 'S2_AWEIsh.tif'), 'w', **profile) as dst:
            dst.write(aweish.astype(np.float32), 1)
        
        
        result = upload_file_to_yandex(
            local_path='/tmp/S2_AWEIsh.tif',
            yandex_object_name=f'gee_exports/{foldername}/aweish_{metaname}', 
            bucket_name=YC_BUCKET,
            conn_id=YANDEX_CONN_ID,)
        
        return result
        
# file_path = r'F:\gidromonitor-airflow\dags\indicators\tasks\s2_after_20260920_111856.tif'


# result = calc_aweish(file_path)
    
