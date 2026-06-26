FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir "temporalio>=1.8" "httpx>=0.27" "redis>=5.0"

COPY services/worker/ /app/
ENV PYTHONPATH=/app

CMD ["python", "-m", "moiraflow_worker.main"]
