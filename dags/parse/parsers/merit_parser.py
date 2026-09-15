import ee

PROJECT_ID = 'bustling-psyche-508412-e6'



def parse(point, radius):
    ee.Initialize(project=PROJECT_ID)
    region = ee.Geometry.Point(point).buffer(radius).bounds()
    
    merit_hydro = ee.Image('MERIT/Hydro/v1_0_1')
    merit_selected = merit_hydro.select(['elv', 'dir', 'wth', 'wat', 'upa', 'upg', 'hnd', 'viswth']).toFloat()
    
    try:
        file_prefix = 'MERIT_Hydro'
        
        task_merit = ee.batch.Export.image.toDrive(
            image=merit_selected,
            description='MERIT_export',
            folder='GEE_Exports',
            fileNamePrefix=file_prefix,
            region=region,
            crs='EPSG:32652',
            scale=10,
            maxPixels=1e13,
            fileFormat='GeoTIFF'
        )
        task_merit.start()
        
        print(f"Задача экспорта MERIT запущена ID: {task_merit.id}")
        
    except Exception as e:
        print(f"Ошибка при запуске задачи экспорта MERIT: {e}")

