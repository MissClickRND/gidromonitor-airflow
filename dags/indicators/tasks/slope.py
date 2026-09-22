import rasterio
import os
import matplotlib.pyplot as plt
import numpy as np

from utils.gee_storage import download_file, upload_file_to_yandex

YC_BUCKET = os.getenv("YC_BUCKET")
YANDEX_CONN_ID = os.getenv("YANDEX_CONN_ID")

def calc_slope(url):
    original_filename = url.split('/')[-1]
    foldername = url.split('/')[-2]
    metaname = ''.join(original_filename.split('_')[1:])
    local_input_path = f"/tmp/{original_filename}"
    download_url= f"https://storage.yandexcloud.net/{YC_BUCKET}/{url}"
    file = download_file(url=download_url, local_path=local_input_path)
    
    with rasterio.open(file) as src:
        
        dem = src.read(1).astype(np.float32)
        
        profile = src.profile
            
        if src.nodata is not None:
            dem[dem == src.nodata] = np.nan
        
        dy, dx = np.gradient(dem, 10.0, 10.0)
        
        slope_rad = np.arctan(np.sqrt(dx**2 + dy**2))
        
        slope_deg = np.degrees(slope_rad)

        slope_deg = np.where(np.isnan(dem), np.nan, slope_deg)
        
        
        profile.update(dtype=rasterio.float32, count=1, nodata=np.nan)
        with rasterio.open(os.path.join('/tmp', 'DEM_Slope_degrees.tif'), 'w', **profile) as dst:
            dst.write(slope_deg.astype(np.float32), 1)
            
        result = upload_file_to_yandex(
            local_path='/tmp/DEM_Slope_degrees.tif',
            yandex_object_name=f'gee_exports/{foldername}/slope_{metaname}', 
            bucket_name=YC_BUCKET,
            conn_id=YANDEX_CONN_ID,)
        
        return result