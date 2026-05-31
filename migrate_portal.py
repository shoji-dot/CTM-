"""
migrate_portal.py
実行: python migrate_portal.py
新規テーブル: material_categories, materials, material_tags,
              material_tag_relations, favorites, customer_memos,
              material_versions
既存テーブル: notifications（resource_type / resource_id 列追加）
"""
import sqlite3, os

DB_PATH = os.path.join(os.path.dirname(__file__), "sales_app.db")

DDL = [
    # ── 資料カテゴリ ──────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS material_categories (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        name        TEXT    NOT NULL UNIQUE,
        description TEXT,
        sort_order  INTEGER NOT NULL DEFAULT 0,
        created_at  TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
    )
    """,
    # デフォルトカテゴリ
    """
    INSERT OR IGNORE INTO material_categories (name, sort_order) VALUES
        ('カタログ',    1),
        ('マニュアル',  2),
        ('添付文書',    3),
        ('案内文書',    4),
        ('その他',      5)
    """,

    # ── 資料本体 ──────────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS materials (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        title           TEXT    NOT NULL,
        description     TEXT,
        category_id     INTEGER REFERENCES material_categories(id),
        file_path       TEXT    NOT NULL,
        file_name       TEXT    NOT NULL,
        file_type       TEXT    NOT NULL,          -- pdf / docx / xlsx など
        file_size       INTEGER NOT NULL DEFAULT 0,
        ai_summary      TEXT,                      -- Anthropic APIで生成
        version         INTEGER NOT NULL DEFAULT 1,
        uploaded_by     INTEGER REFERENCES staffs(id),
        from_approval   INTEGER REFERENCES documents(id), -- 承認文書連携
        is_active       INTEGER NOT NULL DEFAULT 1,
        created_at      TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
        updated_at      TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
    )
    """,

    # ── バージョン履歴 ────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS material_versions (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        material_id INTEGER NOT NULL REFERENCES materials(id),
        version     INTEGER NOT NULL,
        file_path   TEXT    NOT NULL,
        file_name   TEXT    NOT NULL,
        file_size   INTEGER NOT NULL DEFAULT 0,
        ai_summary  TEXT,
        uploaded_by INTEGER REFERENCES staffs(id),
        note        TEXT,
        created_at  TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
    )
    """,

    # ── タグマスタ ────────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS material_tags (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        name       TEXT NOT NULL UNIQUE,
        created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
    )
    """,

    # ── タグ紐付け ────────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS material_tag_relations (
        material_id INTEGER NOT NULL REFERENCES materials(id) ON DELETE CASCADE,
        tag_id      INTEGER NOT NULL REFERENCES material_tags(id) ON DELETE CASCADE,
        PRIMARY KEY (material_id, tag_id)
    )
    """,

    # ── お気に入り ────────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS favorites (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        staff_id    INTEGER NOT NULL REFERENCES staffs(id) ON DELETE CASCADE,
        material_id INTEGER NOT NULL REFERENCES materials(id) ON DELETE CASCADE,
        created_at  TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
        UNIQUE (staff_id, material_id)
    )
    """,

    # ── 顧客メモ ──────────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS customer_memos (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        hospital     TEXT NOT NULL,
        doctor_name  TEXT,
        memo         TEXT,
        staff_id     INTEGER REFERENCES staffs(id),
        created_at   TEXT NOT NULL DEFAULT (datetime('now','localtime')),
        updated_at   TEXT NOT NULL DEFAULT (datetime('now','localtime'))
    )
    """,
]

# notifications テーブルへの列追加（既存テーブルを破壊しない）
ALTER_NOTIFICATIONS = [
    "ALTER TABLE notifications ADD COLUMN resource_type TEXT",
    "ALTER TABLE notifications ADD COLUMN resource_id   INTEGER",
]

# インデックス
INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_materials_category  ON materials(category_id)",
    "CREATE INDEX IF NOT EXISTS idx_materials_uploaded  ON materials(uploaded_by)",
    "CREATE INDEX IF NOT EXISTS idx_favorites_staff     ON favorites(staff_id)",
    "CREATE INDEX IF NOT EXISTS idx_favorites_material  ON favorites(material_id)",
    "CREATE INDEX IF NOT EXISTS idx_memos_hospital      ON customer_memos(hospital)",
    "CREATE INDEX IF NOT EXISTS idx_memos_doctor        ON customer_memos(doctor_name)",
    "CREATE INDEX IF NOT EXISTS idx_mtr_material        ON material_tag_relations(material_id)",
    "CREATE INDEX IF NOT EXISTS idx_mtr_tag             ON material_tag_relations(tag_id)",
    "CREATE INDEX IF NOT EXISTS idx_mver_material       ON material_versions(material_id)",
]


def migrate():
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()

    print("=== migrate_portal.py ===")

    for stmt in DDL:
        cur.executescript(stmt)

    for sql in ALTER_NOTIFICATIONS:
        try:
            cur.execute(sql)
            print(f"  ALTER: {sql.split()[-1]} 追加")
        except sqlite3.OperationalError:
            pass  # 既に存在する列はスキップ

    for sql in INDEXES:
        cur.execute(sql)

    con.commit()
    con.close()
    print("✓ マイグレーション完了")


if __name__ == "__main__":
    migrate()
