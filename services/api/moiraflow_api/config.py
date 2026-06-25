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


def get_settings() -> Settings:
    return Settings()
