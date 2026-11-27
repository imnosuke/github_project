FROM python:3.12-slim

WORKDIR /workspace
COPY requirements.txt /tmp/streamlit-requirements.txt
RUN pip install --no-cache-dir -r /tmp/streamlit-requirements.txt \
    && useradd --create-home --uid 1000 streamlit
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    STREAMLIT_SERVER_ADDRESS=0.0.0.0 \
    STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_SERVER_FILE_WATCHER_TYPE=none \
    STREAMLIT_CLIENT_TOOLBAR_MODE=minimal
USER streamlit
