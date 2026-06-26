"""Runtime settings, sourced from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./moiraflow.db")
    temporal_host: str = os.getenv("TEMPORAL_HOST", "localhost:7233")
    temporal_namespace: str = os.getenv("TEMPORAL_NAMESPACE", "default")
    server_task_queue: str = os.getenv("MOIRAFLOW_TASK_QUEUE", "moiraflow-server")
    jwt_secret: str = os.getenv("JWT_SECRET", "dev-insecure-secret-change-me-please-32bytes")
    jwt_expires_seconds: int = int(os.getenv("JWT_EXPIRES_SECONDS", "3600"))
    redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    # Off by default (tests/local); the docker-compose api sets this to "1".
    event_subscriber_enabled: bool = os.getenv("MOIRAFLOW_EVENT_SUBSCRIBER", "0") == "1"


def get_settings() -> Settings:
    return Settings()
