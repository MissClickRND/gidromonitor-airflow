import ee

PROJECT_ID = 'bustling-psyche-508412-e6'
ee.Initialize(project=PROJECT_ID)

point = [127.50, 50.25]
radius = 5000
target_date = '2019-06-01'

def mask_s2_scl(image):
    """
    Коды SCL: 3=тень облака, 8=облака (средняя вер.), 9=облака (высокая вер.), 
              10=перистые облака, 11=снег/лед
    """
    scl = image.select('SCL')
    mask = scl.neq(3).And(scl.neq(8)).And(scl.neq(9)).And(scl.neq(10)).And(scl.neq(11))
    
    return image.updateMask(mask).divide(10000)

def parse(point, radius, target_date):
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
        return

    # Функция для выбора нужных каналов: B2 (Blue), B3 (Green), B4 (Red), B8 (NIR), B11 (SWIR), SCL (Mask)
    def select_bands(image):
        return image.select(['B2','B3', 'B4', 'B8', 'B11', 'SCL'])

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
    
    def get_date(image):
        return ee.Date(image.get('system:time_start')).format('YYYY-MM-dd').getInfo()

    try:
        date_before = get_date(s2_before)
        print(f"Ближайший снимок S2 ДО {target_date}: {date_before}")
        
        img_before = mask_s2_scl(s2_before)
        img_before_selected = select_bands(img_before)
        
        task_before = ee.batch.Export.image.toDrive(
            image=img_before_selected,
            description=f'S2_before_{date_before}',
            folder='GEE_Exports',
            fileNamePrefix=f'S2_before_{date_before}',
            region=region,
            scale=10,
            maxPixels=1e13,
            fileFormat='GeoTIFF'
        )
        task_before.start()
        print(f"Задача экспорта ДО запущена ID: {task_before.id}")
    except Exception as e:
        print(f"Снимок S2 ДО {target_date} не найден или полностью закрыт облаками: {e}")
    
    try:
        date_after = get_date(s2_after)
        print(f"Ближайший снимок S2 ПОСЛЕ {target_date}: {date_after}")
        
        img_after = mask_s2_scl(s2_after)
        img_after_selected = select_bands(img_after)
        
        task_after = ee.batch.Export.image.toDrive(
            image=img_after_selected,
            description=f'S2_after_{date_after}',
            folder='GEE_Exports',
            fileNamePrefix=f'S2_after_{date_after}',
            region=region,
            scale=10,
            maxPixels=1e13,
            fileFormat='GeoTIFF'
        )
        task_after.start()
        print(f"Задача экспорта ПОСЛЕ запущена ID: {task_after.id}")
    except Exception as e:
        print(f"Снимок S2 ПОСЛЕ {target_date} не найден или полностью закрыт облаками: {e}")



parse(point, radius, target_date)