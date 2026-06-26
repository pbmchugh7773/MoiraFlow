FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir \
    "pydantic>=2.6" "pyyaml>=6.0" "fastapi>=0.110" "uvicorn[standard]>=0.27" \
    "sqlalchemy>=2.0" "alembic>=1.13" "temporalio>=1.8" "psycopg[binary]>=3.1" \
    "argon2-cffi>=23" "pyjwt>=2.8" "redis>=5.0" "cryptography>=42.0" "prometheus-client>=0.20"

COPY services/api/ /app/
ENV PYTHONPATH=/app

EXPOSE 8000
# Apply migrations, then serve. Migrations are idempotent across restarts/replicas.
CMD ["sh", "-c", "alembic upgrade head && uvicorn moiraflow_api.main:app --host 0.0.0.0 --port 8000"]
