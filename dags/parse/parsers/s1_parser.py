import os
import ee
import json
from utils.gee_storage import download_and_upload_to_yandex
from utils.file_utils import S1_BANDS_CONFIG

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

def parse_s1(point, radius, target_date):
    init_ee()
    region = ee.Geometry.Point(point).buffer(radius).bounds()
    
    date_ee = ee.Date(target_date)
    start_date = date_ee.advance(-30, 'day').format('YYYY-MM-dd').getInfo()
    end_date = date_ee.advance(30, 'day').format('YYYY-MM-dd').getInfo()
    
    s1_collection = (ee.ImageCollection('COPERNICUS/S1_GRD')
        .filterBounds(region)
        .filterDate(start_date, end_date)
        .filter(ee.Filter.eq('instrumentMode', 'IW'))
        .filter(ee.Filter.listContains('transmitterReceiverPolarisation', 'VV'))
        .filter(ee.Filter.listContains('transmitterReceiverPolarisation', 'VH'))
    )
    
    s1_count = s1_collection.size().getInfo()
    if s1_count == 0:
        print("Нет данных. Попробуйте расширить окно поиска")
        return None
    
    s1_before = (s1_collection
        .filter(ee.Filter.lt('system:time_start', date_ee.millis()))
        .sort('system:time_start', False)
        .first()
    )
    
    s1_after = (s1_collection
        .filter(ee.Filter.gte('system:time_start', date_ee.millis()))
        .sort('system:time_start', True)
        .first()
    )
    
    def download_image(image, prefix):
        try:
            date_str = ee.Date(image.get('system:time_start')).format('YYYY-MM-dd').getInfo()
            print(f"Ближайший снимок {prefix.upper()} {target_date}: {date_str}")
            
            img_to_download = image.select(['VV', 'VH'])

            params = {
                'region': region,
                'crs': 'EPSG:32652',
                'scale': 10,
                'fileFormat': 'GEO_TIFF'
            }
            
            url = img_to_download.getDownloadURL(params)
            
            result_path = download_and_upload_to_yandex(
                url=url,
                bucket_name=YC_BUCKET,
                conn_id=YANDEX_CONN_ID,
                folder_prefix=f's1_{prefix}',
                file_extension='.tif',
                bands_config=S1_BANDS_CONFIG,
            )
            
            return result_path
            
        except Exception as e:
            print(f"Снимок {prefix.upper()} {target_date} не найден или ошибка обработки: {e}")
            return None

    path_before = download_image(s1_before, 'before')
    path_after = download_image(s1_after, 'after')
    
    return {
        'before': path_before,
        'after': path_after
    }