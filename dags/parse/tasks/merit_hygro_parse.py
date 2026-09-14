import ee

PROJECT_ID = 'bustling-psyche-508412-e6'
ee.Initialize(project=PROJECT_ID)

point = [127.50, 50.25]
radius = 5000
target_date = '2019-01-01'

def parse(point, radius, target_date):
    region = ee.Geometry.Point(point).buffer(radius).bounds()
    
    merit_hydro = ee.Image('MERIT/Hydro/v1_0_1')
    
    # - elv: Elevation (высота над уровнем моря, м)
    # - dir: Flow Direction (направление потока)
    # - wth: River channel width (ширина русла реки)
    # - wat: Land and permanent water (суша=0, вода=1)
    # - upa: Upstream drainage area (площадь водосбора, км²)
    # - upg: Upstream drainage pixel (количество пикселей выше по течению)
    # - hnd: Height above nearest drainage (высота над ближайшим дренажом, м)
    # - viswth: Visualization of river channel width (визуализация ширины русла)
    merit_selected = merit_hydro.select(['elv', 'dir', 'wth', 'wat', 'upa', 'upg', 'hnd', 'viswth']).toFloat()
    
    try:
        safe_date = target_date.replace('-', '')
        file_prefix = f'MERIT_Hydro_{target_date}'
        
        task_merit = ee.batch.Export.image.toDrive(
            image=merit_selected,
            description=f'MERIT_Hydro_export_{safe_date}',
            folder='GEE_Exports',
            fileNamePrefix=file_prefix,
            region=region,
            scale=90,
            maxPixels=1e13,
            fileFormat='GeoTIFF'
        )
        task_merit.start()
        
        print(f"Задача экспорта MERIT Hydro запущена ID: {task_merit.id}")
        
    except Exception as e:
        print(f"Ошибка при запуске задачи экспорта MERIT Hydro: {e}")


parse(point, radius, target_date)