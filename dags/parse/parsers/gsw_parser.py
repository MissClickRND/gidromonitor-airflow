import ee

PROJECT_ID = 'bustling-psyche-508412-e6'


def parse_gsw(point, radius):
    ee.Initialize(project=PROJECT_ID)
    region = ee.Geometry.Point(point).buffer(radius).bounds()
    
    gsw = ee.Image('JRC/GSW1_4/GlobalSurfaceWater')
    gsw_selected = gsw.select([ 'occurrence', 'change_abs', 'change_norm', 'transition', 
                                'max_extent', 'recurrence', 'seasonality']).toFloat()
    
    try:
        file_prefix = 'GSW_1_4'
        
        task_gsw = ee.batch.Export.image.toDrive(
            image=gsw_selected,
            description='GSW_export',
            folder='GEE_Exports',
            fileNamePrefix=file_prefix,
            region=region,
            crs='EPSG:32652',
            scale=10,
            maxPixels=1e13,
            fileFormat='GeoTIFF'
        )
        task_gsw.start()
        
        print(f"Задача экспорта GSW запущена ID: {task_gsw.id}")
        
    except Exception as e:
        print(f"Ошибка при запуске задачи экспорта GSW: {e}")

