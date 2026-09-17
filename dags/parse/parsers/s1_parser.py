import ee


PROJECT_ID = 'bustling-psyche-508412-e6'

def parse_s1(point, radius, target_date):
    ee.Initialize(project=PROJECT_ID)
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
        return
    
    def select_vv_vh(image):
        return image.select(['VV', 'VH'])
    
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
    
    def get_date(image):
        return ee.Date(image.get('system:time_start')).format('YYYY-MM-dd').getInfo()
    
    try:
        date_before = get_date(s1_before)
        print(f"Ближайший снимок ДО {target_date}: {date_before}")
        task_before = ee.batch.Export.image.toDrive(
            image=select_vv_vh(s1_before),
            description=f'S1_before_{date_before}',
            folder='GEE_Exports',
            crs='EPSG:32652',
            fileNamePrefix=f'S1_before_{date_before}',
            region=region, scale=10, maxPixels=1e13, fileFormat='GeoTIFF'
        )
        task_before.start()
        print(f"Задача экспорта ДО запущена ID: {task_before.id}")
    except Exception as e:
        print(f"Снимок ДО {target_date} не найден: {e}")
    
    try:
        date_after = get_date(s1_after)
        print(f"Ближайший снимок ПОСЛЕ {target_date}: {date_after}")
        task_after = ee.batch.Export.image.toDrive(
            image=select_vv_vh(s1_after),
            description=f'S1_after_{date_after}',
            folder='GEE_Exports',
            crs='EPSG:32652',
            fileNamePrefix=f'S1_after_{date_after}',
            region=region, scale=10, maxPixels=1e13, fileFormat='GeoTIFF'
        )
        task_after.start()
        print(f"Задача экспорта ПОСЛЕ запущена ID: {task_after.id}")
    except Exception as e:
        print(f"Снимок ПОСЛЕ {target_date} не найден: {e}")
