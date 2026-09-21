import os
import ee
import json
from utils.gee_storage import download_and_upload_to_yandex
from utils.file_utils import GSW_BANDS_CONFIG

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

def parse_gsw(point, radius):
    init_ee()
    
    region = ee.Geometry.Point(point).buffer(radius).bounds()
    
    image = (
        ee.Image('JRC/GSW1_4/GlobalSurfaceWater')
        .select([
            'occurrence', 'change_abs', 'change_norm',
            'transition', 'max_extent', 'recurrence', 'seasonality',
        ])
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
        folder_prefix='gsw',
        file_extension='.tif',
        bands_config=GSW_BANDS_CONFIG,
    )
    
    return result_path