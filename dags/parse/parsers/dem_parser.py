import ee

PROJECT_ID = 'bustling-psyche-508412-e6'


def parse_dem(point, radius):
    ee.Initialize(project=PROJECT_ID)
    region = ee.Geometry.Point(point).buffer(radius).bounds()
    
    dem_collection = ee.ImageCollection('COPERNICUS/DEM/GLO30_2024_1')
    dem_image = dem_collection.mosaic()
    dem_selected = dem_image.select(['DEM', 'HEM', 'WBM']).toFloat()
    
    try:
        file_prefix = 'DEM_GLO30'
        
        task_dem = ee.batch.Export.image.toDrive(
            image=dem_selected,
            description='DEM_export',
            folder='GEE_Exports',
            fileNamePrefix=file_prefix,
            region=region,
            crs='EPSG:32652',
            scale=10,
            maxPixels=1e13,
            fileFormat='GeoTIFF'
        )
        task_dem.start()
        
        print(f"Задача экспорта DEM запущена ID: {task_dem.id}")
        
    except Exception as e:
        print(f"Ошибка при запуске задачи экспорта DEM: {e}")

