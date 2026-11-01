#!/bin/bash
set -e

echo "=== [1/4] Nâng cấp Superset Metadata Database ==="
superset db upgrade

echo "=== [2/4] Khởi tạo tài khoản Admin cho Superset ==="
superset fab create-admin \
    --username "${SUPERSET_ADMIN_USER:-admin}" \
    --firstname Superset \
    --lastname Admin \
    --email admin@example.com \
    --password "${SUPERSET_ADMIN_PASSWORD:-admin}" || true

echo "=== [3/4] Khởi tạo Roles và Permissions mặc định ==="
superset init

echo "=== [4/4] Tự động kết nối ClickHouse (Bronze / Silver / Gold) ==="
python /app/bootstrap_clickhouse.py || true

echo "=== Khởi động Superset Server trên cổng 8088 ==="
exec /usr/bin/run-server.sh

