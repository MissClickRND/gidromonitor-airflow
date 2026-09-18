FROM apache/airflow:3.3.1-python3.11


COPY requirements.txt /opt/airflow/
RUN pip install --no-cache-dir -r /opt/airflow/requirements.txt
