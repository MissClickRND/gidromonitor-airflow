import os
from airflow import DAG
from airflow.providers.standard.operators.python import PythonOperator
from datetime import datetime

from indicators.tasks.vv_vh import calc_vv_vh
from indicators.tasks.occurrence import calc_occurrence
from indicators.tasks.seasonality import calc_seasonality
from indicators.tasks.slope import calc_slope
from indicators.tasks.aweish import calc_aweish
from indicators.tasks.mndwi import calc_mndwi
from indicators.tasks.hand import calc_hand
from indicators.tasks.ndwi import calc_ndwi
from indicators.tasks.ndvi import calc_ndvi

from utils.gee_storage import merge_layers_to_geotiff 

default_args = {
    'owner': 'airflow',
    'start_date': datetime(2023, 1, 1),
}

def run_calc_hand(**context):
    url = context['dag_run'].conf.get('merit_url')
    if not url:
        raise ValueError("Не передан merit_url в conf")
    return calc_hand(url=url)

def run_calc_slope(**context):
    url = context['dag_run'].conf.get('dem_url')
    if not url:
        raise ValueError("Не передан dem_url в conf")
    return calc_slope(url=url)

def run_calc_seasonality(**context):
    url = context['dag_run'].conf.get('gsw_url')
    if not url:
        raise ValueError("Не передан gsw_url в conf")
    return calc_seasonality(url=url)

def run_calc_occurrence(**context):
    url = context['dag_run'].conf.get('gsw_url')
    if not url:
        raise ValueError("Не передан gsw_url в conf")
    return calc_occurrence(url=url)

def run_calc_vv_vh(**context):
    url = context['dag_run'].conf.get('s1_before_url')
    if not url:
        raise ValueError("Не передан s1_before_url в conf")
    return calc_vv_vh(url=url)

def run_calc_ndvi(**context):
    url = context['dag_run'].conf.get('s2_before_url')
    if not url:
        raise ValueError("Не передан s2_before_url в conf")
    return calc_ndvi(url=url)

def run_calc_ndwi(**context):
    url = context['dag_run'].conf.get('s2_before_url')
    return calc_ndwi(url=url)

def run_calc_mndwi(**context):
    url = context['dag_run'].conf.get('s2_before_url')
    return calc_mndwi(url=url)

def run_calc_aweish(**context):
    url = context['dag_run'].conf.get('s2_before_url')
    return calc_aweish(url=url)

def run_merge_layers(**context):
    ti = context['ti']
    
    layers_dict = {
        'HAND': ti.xcom_pull(task_ids='calc_hand'),
        'NDVI': ti.xcom_pull(task_ids='calc_ndvi'),
        'NDWI': ti.xcom_pull(task_ids='calc_ndwi'),
        'MNDWI': ti.xcom_pull(task_ids='calc_mndwi'),
        'AWEISH': ti.xcom_pull(task_ids='calc_aweish'),
        'SLOPE': ti.xcom_pull(task_ids='calc_slope'),
        'VV_VH': ti.xcom_pull(task_ids='calc_vv_vh'),
        'OCCURRENCE': ti.xcom_pull(task_ids='calc_occurrence'),
        'SEASONALITY': ti.xcom_pull(task_ids='calc_seasonality'),
    }
    
    layers_dict = {k: v for k, v in layers_dict.items() if v is not None}
    
    if not layers_dict:
        raise ValueError("Не удалось получить пути к слоям из XCom")
        
    bucket_name = os.getenv("YC_BUCKET")
    conn_id = os.getenv("YANDEX_CONN_ID")
    
    folder_prefix = context['dag_run'].conf.get('folder_prefix', 'merged')
    
    return merge_layers_to_geotiff(
        layers_dict=layers_dict,
        bucket_name=bucket_name,
        conn_id=conn_id,
        folder_prefix=folder_prefix,
        file_extension=".tif"
    )


with DAG(
    dag_id='gee_indicators',
    default_args=default_args,
    schedule=None,
    catchup=False,
    tags=['gee', 'indicators'],
) as dag:

    task_hand = PythonOperator(task_id='calc_hand', python_callable=run_calc_hand)
    task_ndvi = PythonOperator(task_id='calc_ndvi', python_callable=run_calc_ndvi)
    task_ndwi = PythonOperator(task_id='calc_ndwi', python_callable=run_calc_ndwi)
    task_mndwi = PythonOperator(task_id='calc_mndwi', python_callable=run_calc_mndwi)
    task_aweish = PythonOperator(task_id='calc_aweish', python_callable=run_calc_aweish)
    task_slope = PythonOperator(task_id='calc_slope', python_callable=run_calc_slope)
    task_vv_vh = PythonOperator(task_id='calc_vv_vh', python_callable=run_calc_vv_vh)
    task_occurrence = PythonOperator(task_id='calc_occurrence', python_callable=run_calc_occurrence)
    task_seasonality = PythonOperator(task_id='calc_seasonality', python_callable=run_calc_seasonality)
    
    
    task_merge = PythonOperator(
        task_id='merge_all_layers', 
        python_callable=run_merge_layers
    )


    [task_hand, task_ndvi, task_ndwi, task_mndwi, task_aweish, task_slope, task_vv_vh, task_occurrence, task_seasonality] >> task_merge