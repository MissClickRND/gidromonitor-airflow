import os
import ee
import json

from utils.gee_tiled_download import tiled_download_and_upload
from utils.geojson_utils import geojson_to_ee_geometry
from utils.file_utils import DEM_BANDS_CONFIG

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

def parse_dem(id, polygon):
    init_ee()
    
    geom = geojson_to_ee_geometry(polygon)
    
    image = (
        ee.ImageCollection('COPERNICUS/DEM/GLO30_2024_1')
        .mosaic()
        .select(['DEM'])
        .toFloat()
    )
    
    result_path = tiled_download_and_upload(
        image=image,
        geometry=geom,
        download_params={
            "crs": "EPSG:32652",
            "scale": 10,
            "fileFormat": "GEO_TIFF",
        },
        bucket_name=YC_BUCKET,
        conn_id=YANDEX_CONN_ID,
        folder_prefix=f'{id}/DEM',
        tile_size_deg=0.25,
        bands_config=DEM_BANDS_CONFIG,
        clip_to_original=True,
    )
    
    return result_path