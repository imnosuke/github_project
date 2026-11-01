FROM apache/superset:3.1.3

USER root

# Cài đặt driver chính thức của ClickHouse cho SQLAlchemy / Superset
RUN pip install --no-cache-dir "clickhouse-connect==0.7.19"

COPY bootstrap_clickhouse.py /app/bootstrap_clickhouse.py
COPY superset_init.sh /app/superset_init.sh
RUN sed -i 's/\r$//' /app/superset_init.sh && chmod +x /app/superset_init.sh

USER superset

ENTRYPOINT ["/app/superset_init.sh"]

