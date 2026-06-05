import os
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

# Railway は DATABASE_URL 環境変数を自動設定する
# ローカル開発は SQLite にフォールバック
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./sales_app.db")

# Railway PostgreSQL は "postgres://" を返すが SQLAlchemy は "postgresql://" が必要
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False, "timeout": 30}
    )

    # [C3] SQLite は接続ごとに外部キー制約を有効化する必要がある
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

else:
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
