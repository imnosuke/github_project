FROM apache/airflow:2.9.3-python3.11

USER airflow
COPY requirements.txt /requirements.txt
RUN pip install --no-cache-dir -r /requirements.txt && \
    python -m venv /opt/airflow/dbt_venv && \
    /opt/airflow/dbt_venv/bin/pip install --no-cache-dir --upgrade pip && \
    /opt/airflow/dbt_venv/bin/pip install --no-cache-dir \
        "dbt-core==1.8.8" \
        "dbt-clickhouse==1.8.4"
