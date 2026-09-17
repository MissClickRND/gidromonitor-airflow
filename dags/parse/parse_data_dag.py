from airflow import DAG
from airflow.operators.python import PythonOperator
from datetime import datetime

<<<<<<< HEAD
import sys
import os
from pathlib import Path


current_dir = Path(__file__).parent
if str(current_dir) not in sys.path:
    sys.path.insert(0, str(current_dir))


from parsers.dem_parser import parse_dem
from parsers.gsw_parser import parse_gsw
from parsers.merit_parser import parse_merit
from parsers.s1_parser import parse_s1
from parsers.s2_parser import parse_s2
=======
from .parsers.dem_parser import parse_dem
from .parsers.gsw_parser import parse_gsw
from .parsers.merit_parser import parse_merit
from .parsers.s1_parser import parse_s1
from .parsers.s2_parser import parse_s2
>>>>>>> 6cb19e3a1645b940a9a6bf4c7c7c1a6c96d08451

POINT = [127.50, 50.25]
RADIUS = 5000

default_args = {
    'owner': 'airflow',
    'start_date': datetime(2023, 1, 1),
    'retries': 1,
}

with DAG(
    dag_id='gee_geospatial_data_export',
    default_args=default_args,
    schedule_interval='@daily',
    catchup=False,
    tags=['gee', 'parsers'],
) as dag:

    
    task_dem = PythonOperator(
        task_id='export_dem',
        python_callable=parse_dem,
        op_kwargs={'point': POINT, 'radius': RADIUS},
    )

    task_gsw = PythonOperator(
        task_id='export_gsw',
        python_callable=parse_gsw,
        op_kwargs={'point': POINT, 'radius': RADIUS},
    )

    task_merit = PythonOperator(
        task_id='export_merit',
        python_callable=parse_merit,
        op_kwargs={'point': POINT, 'radius': RADIUS},
    )

    
    task_s1 = PythonOperator(
        task_id='export_sentinel1',
        python_callable=parse_s1,
        op_kwargs={'point': POINT, 'radius': RADIUS, 'target_date': '{{ ds }}'},
    )

    task_s2 = PythonOperator(
        task_id='export_sentinel2',
        python_callable=parse_s2,
        op_kwargs={'point': POINT, 'radius': RADIUS, 'target_date': '{{ ds }}'},
    )

    [task_dem, task_gsw, task_merit, task_s1, task_s2]