import ee

PROJECT_ID = 'bustling-psyche-508412-e6'
ee.Initialize(project=PROJECT_ID)

point = [127.50, 50.25]
radius = 5000
target_date = '2019-01-01'

def parse(point, radius, target_date):
    region = ee.Geometry.Point(point).buffer(radius).bounds()
    
    gsw = ee.Image('JRC/GSW1_4/GlobalSurfaceWater')
    

    # - occurrence: частота появления воды (0-100%)
    # - change: тип изменения водного покрова (0-4)
    # - transition: числовой код перехода между состояниями воды
    # - max_extent: максимальная протяжённость водного покрова
    # - recurrence: повторяемость появления воды (0-100%)
    # - seasonality: сезонность воды (количество месяцев с водой, 0-12)
    gsw_selected = gsw.select([ 'occurrence', 'change_abs', 'change_norm', 'transition', 
                                'max_extent', 'recurrence', 'seasonality']).toFloat()
    
    try:
        safe_date = target_date.replace('-', '')
        file_prefix = f'GSW_1_4_{target_date}'
        
        task_gsw = ee.batch.Export.image.toDrive(
            image=gsw_selected,
            description=f'GSW_export_{safe_date}',
            folder='GEE_Exports',
            fileNamePrefix=file_prefix,
            region=region,
            scale=30,
            maxPixels=1e13,
            fileFormat='GeoTIFF'
        )
        task_gsw.start()
        
        print(f"Задача экспорта JRC запущена ID: {task_gsw.id}")
        
    except Exception as e:
        print(f"Ошибка при запуске задачи экспорта JRC GSW: {e}")


parse(point, radius, target_date)