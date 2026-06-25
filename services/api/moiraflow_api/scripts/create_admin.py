"""Create the initial admin user (and default tenant). Idempotent.

Run: `python -m moiraflow_api.scripts.create_admin`
Reads ADMIN_EMAIL / ADMIN_PASSWORD from the environment.
"""

from __future__ import annotations

import os

from sqlalchemy import select

from ..config import get_settings
from ..db import models
from ..db.session import make_engine, make_session_factory
from ..services import users as user_svc


def main() -> None:
    settings = get_settings()
    factory = make_session_factory(make_engine(settings.database_url))
    email = os.getenv("ADMIN_EMAIL", "admin@moiraflow.local")
    password = os.getenv("ADMIN_PASSWORD", "admin")

    with factory() as session:
        tenant = session.scalar(select(models.Tenant).where(models.Tenant.slug == "default"))
        if tenant is None:
            tenant = models.Tenant(name="Default", slug="default")
            session.add(tenant)
            session.flush()
        if user_svc.get_user_by_email(session, tenant.id, email) is not None:
            print(f"admin already exists: {email}")
            return
        user_svc.create_user(session, tenant.id, email, password, role="admin")
        session.commit()
        print(f"created admin: {email}")


if __name__ == "__main__":
    main()
