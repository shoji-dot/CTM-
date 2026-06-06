"""
pytest共通フィクスチャ。

注意: sqlite:///:memory: は接続ごとに独立したDBを作るため
StaticPool で全接続を同じ in-memory DB に固定する。
これにより middleware の SessionLocal() も同じ DB を参照できる。
"""

import os

os.environ["SECRET_KEY"] = "pytest-test-secret-key-12345678"
os.environ["SESSION_SECRET_KEY"] = "pytest-test-secret-key-12345678"
os.environ["ADMIN_INITIAL_PASSWORD"] = "pytest-admin-password-12345"
# database.py がモジュールロード時に PostgreSQL に接続しないよう SQLite を強制
os.environ["DATABASE_URL"] = "sqlite:///./pytest_test.db"

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# StaticPool: すべての接続で同じ in-memory DB を共有
_test_engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

@event.listens_for(_test_engine, "connect")
def _set_fk(dbapi_conn, rec):
    dbapi_conn.execute("PRAGMA foreign_keys=ON")

_TestSession = sessionmaker(autocommit=False, autoflush=False, bind=_test_engine)

# database モジュールを差し替え（main.py より先にパッチ）
import database as _db
_db.engine = _test_engine
_db.SessionLocal = _TestSession

def _test_get_db():
    s = _TestSession()
    try:
        yield s
    finally:
        s.close()

_db.get_db = _test_get_db

from models import Base
Base.metadata.create_all(bind=_test_engine)

from main import app
from database import get_db
from fastapi.testclient import TestClient

import pytest
import models
from auth import hash_password, create_session_token


@pytest.fixture(autouse=True)
def reset_db():
    """各テスト前に全テーブルをクリア。"""
    with _test_engine.connect() as conn:
        conn.execute(text("PRAGMA foreign_keys=OFF"))
        for tbl in reversed(Base.metadata.sorted_tables):
            conn.execute(tbl.delete())
        conn.execute(text("PRAGMA foreign_keys=ON"))
        conn.commit()
    yield


@pytest.fixture
def db():
    s = _TestSession()
    yield s
    s.close()


@pytest.fixture
def client():
    app.dependency_overrides[get_db] = _test_get_db
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def admin_staff(db):
    staff = models.Staff(
        name="テスト管理者",
        login_id="testadmin",
        password_hash=hash_password("testpass123"),
        role="admin",
        is_active=True,
    )
    db.add(staff)
    db.commit()
    db.refresh(staff)
    return staff


@pytest.fixture
def auth_client(client, admin_staff):
    """Returns (client, staff)"""
    token = create_session_token(admin_staff.id)
    client.cookies.set("session", token)
    return client, admin_staff


@pytest.fixture
def sample_customer(db):
    c = models.Customer(name="テスト病院", category="hospital")
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


@pytest.fixture
def sample_product(db):
    p = models.Product(name="テスト商品", category="医療機器", unit_price=10000)
    db.add(p)
    db.flush()
    inv = models.Inventory(product_id=p.id, current_stock=0)
    db.add(inv)
    db.commit()
    db.refresh(p)
    return p
