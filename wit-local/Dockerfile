# Локальный Wit.ai-совместимый классификатор сообщений NIKA.
FROM python:3.12-slim
WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
ENV KB_DIR=/kb DATA_DIR=/data SC_SERVER_URL=ws://problem-solver:8090 PYTHONUNBUFFERED=1
EXPOSE 8095
HEALTHCHECK --interval=10s --timeout=5s --start-period=20s CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8095/health')"
CMD ["uvicorn", "app.server:app", "--host", "0.0.0.0", "--port", "8095"]
