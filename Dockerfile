FROM apache/airflow:2.9.3-python3.11

USER airflow
COPY requirements.txt /requirements.txt
RUN pip install --no-cache-dir "apache-airflow==2.9.3" -r /requirements.txt \
        --constraint https://raw.githubusercontent.com/apache/airflow/constraints-2.9.3/constraints-3.11.txt && \
    python -m venv /opt/airflow/dbt_venv && \
    /opt/airflow/dbt_venv/bin/pip install --no-cache-dir --upgrade pip && \
    /opt/airflow/dbt_venv/bin/pip install --no-cache-dir \
        "dbt-core==1.8.8" \
        "dbt-clickhouse==1.8.4"
