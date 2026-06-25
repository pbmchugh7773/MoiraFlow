import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from moiraflow_api.db import models
from moiraflow_api.db.base import Base
from moiraflow_api.services import users as svc


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


@pytest.fixture
def tenant(session):
    t = models.Tenant(name="Default", slug="default")
    session.add(t)
    session.flush()
    return t


def test_create_user_hashes_password(session, tenant):
    user = svc.create_user(session, tenant.id, "a@x.io", "pw", role="developer")
    assert user.role == "developer"
    assert user.password_hash != "pw"


def test_duplicate_email_raises(session, tenant):
    svc.create_user(session, tenant.id, "a@x.io", "pw")
    with pytest.raises(svc.UserExistsError):
        svc.create_user(session, tenant.id, "a@x.io", "pw")


def test_authenticate_success(session, tenant):
    svc.create_user(session, tenant.id, "a@x.io", "pw")
    user = svc.authenticate(session, tenant.id, "a@x.io", "pw")
    assert user is not None


def test_authenticate_wrong_password_returns_none(session, tenant):
    svc.create_user(session, tenant.id, "a@x.io", "pw")
    assert svc.authenticate(session, tenant.id, "a@x.io", "nope") is None


def test_authenticate_inactive_user_returns_none(session, tenant):
    user = svc.create_user(session, tenant.id, "a@x.io", "pw")
    user.is_active = False
    session.flush()
    assert svc.authenticate(session, tenant.id, "a@x.io", "pw") is None


def test_authenticate_unknown_email_returns_none(session, tenant):
    assert svc.authenticate(session, tenant.id, "ghost@x.io", "pw") is None


def test_get_unknown_user_raises(session):
    with pytest.raises(svc.UserNotFoundError):
        svc.get_user(session, uuid.uuid4())
