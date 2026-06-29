FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir "temporalio>=1.8" "httpx>=0.27" "redis>=5.0" \
    "sqlalchemy>=2.0" "psycopg[binary]>=3.1" "cryptography>=42.0" "boto3>=1.34" \
    "defusedxml>=0.7"

COPY services/worker/ /app/
ENV PYTHONPATH=/app

# Run as a non-root user so `command` jobs execute unprivileged (docs 05 §4.4).
RUN useradd -m -u 10001 moiraflow
USER moiraflow

CMD ["python", "-m", "moiraflow_worker.main"]
