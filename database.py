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
    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,
        pool_size=5,        # 常時保持する接続数
        max_overflow=10,    # 超過時に追加できる接続数（最大15接続）
        pool_timeout=30,    # 接続取得タイムアウト（秒）
        pool_recycle=1800,  # 30分で接続を再生成（Railway側の切断対策）
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
