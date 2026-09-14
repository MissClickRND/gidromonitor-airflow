import ee

PROJECT_ID = 'bustling-psyche-508412-e6'
ee.Initialize(project=PROJECT_ID)

test_point = ee.Geometry.Point([127.50, 50.25])
test_square = test_point.buffer(2000).bounds() 
region = test_square

start_date = '2019-01-01'
end_date = '2021-12-31'


glo30_collection = (ee.ImageCollection('COPERNICUS/DEM/GLO30_2024_1')
    .filterBounds(region)
)


glo30_count = glo30_collection.size().getInfo()
print(f" Найдено изображений GLO30: {glo30_count}")

if glo30_count > 0:
    glo30_dem = glo30_collection.select(['DEM']).mosaic().clip(region)
    
    task_glo30 = ee.batch.Export.image.toDrive(
        image=glo30_dem,
        description='GLO30_DEM_Export',
        folder='GEE_Exports',
        fileNamePrefix='GLO30_Test_30m',
        region=region,
        scale=30,
        maxPixels=1e13,
        fileFormat='GeoTIFF'
    )
    task_glo30.start()
    print(f"Задача GLO30 запущена. ID: {task_glo30.id}")
else:
    print("GLO30: нет данных для указанной области")
    

s1_collection = (ee.ImageCollection('COPERNICUS/S1_GRD')
    .filterBounds(region)
    .filterDate(start_date, end_date)
    .filter(ee.Filter.eq('instrumentMode', 'IW'))
    .filter(ee.Filter.listContains('transmitterReceiverPolarisation', 'VV'))
    .filter(ee.Filter.listContains('transmitterReceiverPolarisation', 'VH'))
)

s2_collection = (ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
    .filterBounds(region)
    .filterDate(start_date, end_date)
    .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 30))
)


s1_count = s1_collection.size().getInfo()
print(f" Найдено изображений Sentinel-1: {s1_count}")

if s1_count > 0:

    def preprocess_s1(image):
        return image.select(['VV', 'VH'])
    
    s1_median = s1_collection.map(preprocess_s1).median()
    
    task_s1 = ee.batch.Export.image.toDrive(
        image=s1_median,
        description='S1_km',
        folder='GEE_Exports',
        fileNamePrefix='S1_km',
        region=region,
        scale=10,
        maxPixels=1e13,
        fileFormat='GeoTIFF'
    )
    task_s1.start()
    print(f"🚀 Задача Sentinel-1 запущена. ID: {task_s1.id}")
else:
    print("Sentinel-1: нет данных за указанный период")


def mask_s2_clouds(image):
    qa = image.select('QA60')
    cloud_bit_mask = 1 << 10
    cirrus_bit_mask = 1 << 11
    mask = qa.bitwiseAnd(cloud_bit_mask).eq(0).And(qa.bitwiseAnd(cirrus_bit_mask).eq(0))
    return image.updateMask(mask).divide(10000)

s2_median = s2_collection.map(mask_s2_clouds).median().select(['B2', 'B3', 'B4', 'B8'])

s2_count = s2_collection.size().getInfo()
print(f"Найдено изображений Sentinel-2: {s2_count}")

if s2_count > 0:
    task_s2 = ee.batch.Export.image.toDrive(
        image=s2_median,
        description='S2_km',
        folder='GEE_Exports',
        fileNamePrefix='S2_km',
        region=region,
        scale=10,
        maxPixels=1e13,
        fileFormat='GeoTIFF'
    )
    task_s2.start()
    print(f"Задача Sentinel-2 запущена. ID: {task_s2.id}")
else:
    print("Sentinel-2: нет данных за указанный период")



print("\n" + "="*50)
print("Проверьте вкладку 'Tasks' на https://code.earthengine.google.com/")
print("="*50)
