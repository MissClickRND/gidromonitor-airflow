import os
import ee
import json
from utils.gee_storage import download_and_upload_to_yandex

GEE_PROJECT = os.getenv("GEE_PROJECT")
GEE_KEY_PATH = os.getenv("GEE_KEY_PATH")
YC_BUCKET = os.getenv("YC_BUCKET")
YANDEX_CONN_ID = os.getenv("YANDEX_CONN_ID")

def init_ee():
    with open(GEE_KEY_PATH) as f:
        service_account_info = json.load(f)
    credentials = ee.ServiceAccountCredentials(
        email=service_account_info['client_email'],
        key_data=service_account_info['private_key']
    )
    ee.Initialize(credentials, project=GEE_PROJECT)

def parse_dem(point, radius):
    init_ee()
    
    region = ee.Geometry.Point(point).buffer(radius).bounds()
    
    image = (
        ee.ImageCollection('COPERNICUS/DEM/GLO30_2024_1')
        .mosaic()
        .select(['DEM'])
        .toFloat()
    )
    
    params = {
        'region': region,
        'crs': 'EPSG:32652',
        'scale': 30,
        'fileFormat': 'GEO_TIFF'
    }
    
    url = image.getDownloadURL(params)
    
    result_path = download_and_upload_to_yandex(
        url=url,
        bucket_name=YC_BUCKET,
        conn_id=YANDEX_CONN_ID,
        folder_prefix='dem',
        file_extension='.tif'
    )
    
    return result_path