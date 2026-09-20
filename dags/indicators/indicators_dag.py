from airflow import DAG
from airflow.providers.standard.operators.python import PythonOperator
from datetime import datetime, timedelta

from indicators.tasks.aweish import calc_aweish
from dags.indicators.tasks.mndwi import calc_mndwi
from dags.indicators.tasks.hand import calc_hand
from dags.indicators.tasks.ndwi import calc_ndwi
from dags.indicators.tasks.ndvi import calc_ndvi

# from dags.indicators.tasks.slope import calc_slope
# from dags.indicators.tasks.vv_vh import calc_vv_vh


default_args = {
    'owner': 'airflow',
    'start_date': datetime(2023, 1, 1),
    # 'retries': 1,
}

with DAG(
    dag_id='gee_indicators',
    default_args=default_args,
    schedule='@daily',
    catchup=False,
    tags=['gee', 'indicators'],
) as dag:

    
    task_aweish = PythonOperator(
        task_id='calc_aweish',
        python_callable=calc_aweish,
        op_kwargs={'url'},
    )

    task_mndwi = PythonOperator(
        task_id='calc_mndwi',
        python_callable=calc_mndwi,
        op_kwargs={'url'},
    )

    task_hand = PythonOperator(
        task_id='calc_hand',
        python_callable=calc_hand,
        op_kwargs={'url'},
    )

    task_ndwi = PythonOperator(
        task_id='calc_ndwi',
        python_callable=calc_ndwi,
        op_kwargs={'url'},
    )

    task_ndvi = PythonOperator(
        task_id='calc_ndvi',
        python_callable=calc_ndvi,
        op_kwargs={'url'},
    )

    # task_slope = PythonOperator(
    #     task_id='calc_slope',
    #     python_callable=calc_slope,
    #     op_kwargs={'url'},
    # )
    
    # task_vv_vh = PythonOperator(
    #     task_id='calc_vv_vh',
    #     python_callable=calc_vv_vh,
    #     op_kwargs={'url'},
    # )
