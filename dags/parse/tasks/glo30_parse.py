import ee

PROJECT_ID = 'bustling-psyche-508412-e6'
ee.Initialize(project=PROJECT_ID)

point = [127.50, 50.25]
radius = 5000
target_date = '2019-01-01'

def parse(point, radius, target_date):
    region = ee.Geometry.Point(point).buffer(radius).bounds()
    
    dem_collection = ee.ImageCollection('COPERNICUS/DEM/GLO30_2024_1')
    dem_image = dem_collection.mosaic()
    

    dem_selected = dem_image.select(['DEM', 'HEM', 'WBM']).toFloat()
    
    try:
        safe_date = target_date.replace('-', '')
        file_prefix = f'DEM_GLO30_{target_date}'
        
        task_dem = ee.batch.Export.image.toDrive(
            image=dem_selected,
            description=f'DEM_export_{safe_date}',
            folder='GEE_Exports',
            fileNamePrefix=file_prefix,
            region=region,
            scale=30,
            maxPixels=1e13,
            fileFormat='GeoTIFF'
        )
        task_dem.start()
        
        print(f"Задача экспорта DEM запущена ID: {task_dem.id}")
        
    except Exception as e:
        print(f"Ошибка при запуске задачи экспорта DEM: {e}")

parse(point, radius, target_date)
