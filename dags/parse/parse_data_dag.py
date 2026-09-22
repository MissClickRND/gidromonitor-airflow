from airflow import DAG
from airflow.providers.standard.operators.python import PythonOperator
from airflow.providers.standard.operators.trigger_dagrun import TriggerDagRunOperator
from datetime import datetime

from parse.parsers.esa_parser import parse_esa
from parse.parsers.dem_parser import parse_dem
from parse.parsers.gsw_parser import parse_gsw
from parse.parsers.merit_parser import parse_merit
from parse.parsers.s1_parser import parse_s1
from parse.parsers.s2_parser import parse_s2

DEFAULT_ID = 'e431b706-e394-433a-a003-caa1ab484038'
DEFAULT_POLYGON = {
    "type": "Feature",
    "geometry": {
        "type": "Polygon",
        "coordinates": [
            [
                [127.23067489282342, 50.128303988501614],
                [127.8493251071766, 50.128303988501614],
                [127.8493251071766, 50.451696011498385],
                [127.23067489282342, 50.451696011498385],
                [127.23067489282342, 50.128303988501614]
            ]
        ]
    },
    "properties": {}
}

DATE_PRE_STR = "2019-07-15"
DATE_PEAK_STR = "2019-07-27"
DATE_PRE = datetime(2019, 7, 15)
DATE_PEAK = datetime(2019, 7, 27)

default_args = {
    'owner': 'airflow',
    'start_date': datetime(2023, 1, 1),
    'retries': 1,
}


def gather_urls_for_next_dag(**context):
    ti = context['ti']
    s1_data = ti.xcom_pull(task_ids='export_sentinel1')
    s2_data = ti.xcom_pull(task_ids='export_sentinel2')

    return {
        'dem_url': ti.xcom_pull(task_ids='export_dem'),
        'gsw_url': ti.xcom_pull(task_ids='export_gsw'),
        'merit_url': ti.xcom_pull(task_ids='export_merit'),
        'esa_url': ti.xcom_pull(task_ids='export_esa'),
        's1_pre_url': s1_data['pre'],
        's1_peak_url': s1_data['peak'],
        's2_pre_url': s2_data['pre'],
        's2_peak_url': s2_data['peak'],
    }


with DAG(
    dag_id='gee_geospatial_data_export',
    default_args=default_args,
    schedule=None,
    catchup=False,
    render_template_as_native_obj=True,
    tags=['gee', 'parsers'],
    params={
        'default_id': DEFAULT_ID,
        'default_polygon': DEFAULT_POLYGON,
        'date_pre': DATE_PRE_STR,
        'date_peak': DATE_PEAK_STR,
    }
) as dag:

    task_dem = PythonOperator(
        task_id='export_dem',
        python_callable=parse_dem,
        op_kwargs={
            'id': "{{ (dag_run.conf or {}).get('id', params.default_id) }}",
            'polygon': "{{ (dag_run.conf or {}).get('polygon', params.default_polygon) }}",
        },
    )

    task_gsw = PythonOperator(
        task_id='export_gsw',
        python_callable=parse_gsw,
        op_kwargs={
            'id': "{{ (dag_run.conf or {}).get('id', params.default_id) }}",
            'polygon': "{{ (dag_run.conf or {}).get('polygon', params.default_polygon) }}",
        },
    )

    task_merit = PythonOperator(
        task_id='export_merit',
        python_callable=parse_merit,
        op_kwargs={
            'id': "{{ (dag_run.conf or {}).get('id', params.default_id) }}",
            'polygon': "{{ (dag_run.conf or {}).get('polygon', params.default_polygon) }}",
        },
    )
    
    task_esa = PythonOperator(
        task_id='export_esa',
        python_callable=parse_esa,
        op_kwargs={
            'id': "{{ (dag_run.conf or {}).get('id', params.default_id) }}",
            'polygon': "{{ (dag_run.conf or {}).get('polygon', params.default_polygon) }}",
        },
    )

    task_s1 = PythonOperator(
        task_id='export_sentinel1',
        python_callable=parse_s1,
        op_kwargs={
            'id': "{{ (dag_run.conf or {}).get('id', params.default_id) }}",
            'polygon': "{{ (dag_run.conf or {}).get('polygon', params.default_polygon) }}",
            'date_pre': "{{ datetime.fromisoformat((dag_run.conf or {}).get('date_pre', params.date_pre)) }}",
            'date_peak': "{{ datetime.fromisoformat((dag_run.conf or {}).get('date_peak', params.date_peak)) }}",
        },
    )

    task_s2 = PythonOperator(
        task_id='export_sentinel2',
        python_callable=parse_s2,
        op_kwargs={
            'id': "{{ (dag_run.conf or {}).get('id', params.default_id) }}",
            'polygon': "{{ (dag_run.conf or {}).get('polygon', params.default_polygon) }}",
            'date_pre': "{{ datetime.fromisoformat((dag_run.conf or {}).get('date_pre', params.date_pre)) }}",
            'date_peak': "{{ datetime.fromisoformat((dag_run.conf or {}).get('date_peak', params.date_peak)) }}",
        },
    )

    gather_task = PythonOperator(
        task_id='gather_exported_urls',
        python_callable=gather_urls_for_next_dag,
    )

    trigger_indicators = TriggerDagRunOperator(
        task_id='trigger_gee_indicators',
        trigger_dag_id='gee_indicators',
        conf="{{ ti.xcom_pull(task_ids='gather_exported_urls') }}",
        wait_for_completion=False,
    )

    [task_dem, task_gsw, task_merit, task_esa, task_s1, task_s2] >> gather_task >> trigger_indicators