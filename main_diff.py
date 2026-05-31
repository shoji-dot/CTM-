# ============================================================
# main.py への追記差分
# 既存の app = FastAPI(...) の直後に追記してください
# ============================================================

# ── 新規ルーター登録 ─────────────────────────────────────────
from material_router       import router as material_router
from customer_memo_router  import router as memo_router
from notification_router   import router as notif_router

app.include_router(material_router)
app.include_router(memo_router)
app.include_router(notif_router)

# ── 静的ファイル配信（uploads ディレクトリ）────────────────────
from fastapi.staticfiles import StaticFiles
import pathlib

uploads_dir = pathlib.Path(__file__).parent / "uploads"
uploads_dir.mkdir(exist_ok=True)
app.mount("/uploads", StaticFiles(directory=str(uploads_dir)), name="uploads")


# ============================================================
# ダッシュボード エンドポイント差分
# 既存の dashboard() 関数内の context dict に以下を追加
# ============================================================

# ---- ダッシュボード用クエリ追加分（get_db() / sqlite3 使用）----
"""
以下を既存ダッシュボード関数の con.execute() 群の末尾に追加してください:

# お気に入り資料（最新5件）
fav_materials = con.execute(
    '''
    SELECT m.id, m.title, m.file_type, m.updated_at, mc.name AS category_name
    FROM favorites f
    JOIN materials m  ON m.id = f.material_id
    LEFT JOIN material_categories mc ON mc.id = m.category_id
    WHERE f.staff_id = ? AND m.is_active=1
    ORDER BY f.created_at DESC LIMIT 5
    ''',
    (staff_id,)
).fetchall()

# 最新通知（未読）
recent_notifs = con.execute(
    "SELECT * FROM notifications WHERE staff_id=? AND is_read=0 ORDER BY created_at DESC LIMIT 5",
    (staff_id,)
).fetchall()

unread_notif_count = con.execute(
    "SELECT COUNT(*) FROM notifications WHERE staff_id=? AND is_read=0",
    (staff_id,)
).fetchone()[0]

# 顧客メモ（最近更新）
recent_memos = con.execute(
    "SELECT * FROM customer_memos ORDER BY updated_at DESC LIMIT 3"
).fetchall()
"""

# そして context dict に追加:
"""
"fav_materials":       fav_materials,
"recent_notifs":       recent_notifs,
"unread_notif_count":  unread_notif_count,
"recent_memos":        recent_memos,
"""


# ============================================================
# サイドメニュー ナビ定義（base.html で使う）
# ============================================================
# テンプレートのグローバル変数として設定するか、
# テンプレート側に直接記述してください。

NAV_MENU = [
    {
        "label": "ダッシュボード",
        "icon":  "grid",
        "url":   "/dashboard",
        "category": None,
    },
    # ── 営業 ──────────────────────────────────
    {"label": "案件管理",   "icon": "briefcase", "url": "/projects",  "category": "営業"},
    {"label": "顧客メモ",   "icon": "book-open", "url": "/customer-memos", "category": "営業"},
    # ── 物流・在庫 ────────────────────────────
    {"label": "在庫管理",   "icon": "package",   "url": "/inventory", "category": "物流・在庫"},
    {"label": "出荷管理",   "icon": "truck",     "url": "/shipments", "category": "物流・在庫"},
    # ── 売上・請求 ────────────────────────────
    {"label": "売上管理",   "icon": "bar-chart", "url": "/sales",     "category": "売上・請求"},
    {"label": "請求管理",   "icon": "file-text", "url": "/invoices",  "category": "売上・請求"},
    # ── 文書・承認 ────────────────────────────
    {"label": "文書管理",   "icon": "folder",    "url": "/approvals", "category": "文書・承認"},
    {"label": "承認ワークフロー", "icon": "check-circle", "url": "/approvals", "category": "文書・承認"},
    # ── 資料 ──────────────────────────────────
    {"label": "資料ライブラリ", "icon": "archive", "url": "/materials", "category": "資料"},
    # ── タスク ────────────────────────────────
    {"label": "タスク管理", "icon": "check-square", "url": "/tasks", "category": "タスク"},
    # ── 管理 ──────────────────────────────────
    {"label": "社員管理",   "icon": "users",     "url": "/staffs",   "category": "管理", "admin_only": True},
]
