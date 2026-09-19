import os
import ee
import json
from parse.utils.gee_storage import download_and_upload_to_yandex


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


def mask_s2_scl(image):
    scl = image.select('SCL')

    mask = scl.neq(3).And(scl.neq(8)).And(scl.neq(9)).And(scl.neq(10)).And(scl.neq(11))
    return image.updateMask(mask).divide(10000)

def parse_s2(point, radius, target_date):
    
    init_ee()
    region = ee.Geometry.Point(point).buffer(radius).bounds()
    
    date_ee = ee.Date(target_date)
    start_date = date_ee.advance(-30, 'day').format('YYYY-MM-dd').getInfo()
    end_date = date_ee.advance(30, 'day').format('YYYY-MM-dd').getInfo()
    
    s2_collection = (ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
        .filterBounds(region)
        .filterDate(start_date, end_date)
        .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 30))
    )

    s2_count = s2_collection.size().getInfo()
    print(f"Найдено снимков S2: {s2_count}")
    
    if s2_count == 0:
        print("Нет данных S2")
        return None

    s2_before = (s2_collection
        .filter(ee.Filter.lt('system:time_start', date_ee.millis()))
        .sort('system:time_start', False)
        .first()
    )
    
    s2_after = (s2_collection
        .filter(ee.Filter.gte('system:time_start', date_ee.millis()))
        .sort('system:time_start', True)
        .first()
    )
    
    def download_image(image, prefix):
        try:
            date_str = ee.Date(image.get('system:time_start')).format('YYYY-MM-dd').getInfo()
            print(f"Ближайший снимок S2 {prefix.upper()} {target_date}: {date_str}")
            
            img_masked = mask_s2_scl(image)
            img_selected = img_masked.select(['B2', 'B3', 'B4', 'B8', 'B11', 'B12', 'SCL'])
            
            params = {
                'region': region,
                'crs': 'EPSG:32652',
                'scale': 10,
                'fileFormat': 'GEO_TIFF'
            }
            
            url = img_selected.getDownloadURL(params)
            
            result_path = download_and_upload_to_yandex(
                url=url,
                bucket_name=YC_BUCKET,
                conn_id=YANDEX_CONN_ID,
                folder_prefix=f's2_{prefix}',
                file_extension='.tif'
            )
            
            return result_path
            
        except Exception as e:
            print(f"Снимок S2 {prefix.upper()} {target_date} не найден или полностью закрыт облаками: {e}")
            return None

    path_before = download_image(s2_before, 'before')
    path_after = download_image(s2_after, 'after')
    

    return {
        'before': path_before,
        'after': path_after
    }