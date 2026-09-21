from airflow import DAG
from airflow.providers.standard.operators.python import PythonOperator
from airflow.providers.standard.operators.trigger_dagrun import TriggerDagRunOperator
from datetime import datetime, timedelta

from parse.parsers.dem_parser import parse_dem
from parse.parsers.gsw_parser import parse_gsw
from parse.parsers.merit_parser import parse_merit
from parse.parsers.s1_parser import parse_s1
from parse.parsers.s2_parser import parse_s2

POINT = [127.50, 50.25]
RADIUS = 5000
TARGET_DATE = datetime(2019, 1, 1)

default_args = {
    'owner': 'airflow',
    'start_date': datetime(2023, 1, 1),
    'retries': 1,
}

def gather_urls_for_next_dag(**context):
    ti = context['ti']
    
    merit_url = ti.xcom_pull(task_ids='export_merit')
    s2_data = ti.xcom_pull(task_ids='export_sentinel2')
    s1_data = ti.xcom_pull(task_ids='export_sentinel1')
    dem_url = ti.xcom_pull(task_ids='export_dem')
    gsw_url = ti.xcom_pull(task_ids='export_gsw')
    
    conf_payload = {
        'merit_url': merit_url,
        'dem_url': dem_url,
        'gsw_url': gsw_url,
    }
    
    if isinstance(s2_data, dict):
        conf_payload['s2_before_url'] = s2_data.get('before')
        conf_payload['s2_after_url'] = s2_data.get('after')
        
    if isinstance(s1_data, dict):
        conf_payload['s1_before_url'] = s1_data.get('before')
        conf_payload['s1_after_url'] = s1_data.get('after')

    return conf_payload

with DAG(
    dag_id='gee_geospatial_data_export',
    default_args=default_args,
    schedule=None,
    catchup=False,
    tags=['gee', 'parsers'],
) as dag:

    task_dem = PythonOperator(task_id='export_dem', python_callable=parse_dem, op_kwargs={'point': POINT, 'radius': RADIUS})
    task_gsw = PythonOperator(task_id='export_gsw', python_callable=parse_gsw, op_kwargs={'point': POINT, 'radius': RADIUS})
    task_merit = PythonOperator(task_id='export_merit', python_callable=parse_merit, op_kwargs={'point': POINT, 'radius': RADIUS})
    task_s1 = PythonOperator(task_id='export_sentinel1', python_callable=parse_s1, op_kwargs={'point': POINT, 'radius': RADIUS, 'target_date': TARGET_DATE})
    task_s2 = PythonOperator(task_id='export_sentinel2', python_callable=parse_s2, op_kwargs={'point': POINT, 'radius': RADIUS, 'target_date': TARGET_DATE})

    gather_task = PythonOperator(
        task_id='gather_exported_urls',
        python_callable=gather_urls_for_next_dag,
    )

    trigger_indicators = TriggerDagRunOperator(
        task_id='trigger_gee_indicators',
        trigger_dag_id='gee_indicators',
        conf="{{ ti.xcom_pull(task_ids='gather_exported_urls') | tojson }}",
        wait_for_completion=False,
    )

    [task_dem, task_gsw, task_merit, task_s1, task_s2] >> gather_task >> trigger_indicators