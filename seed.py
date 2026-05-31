"""
初期データ投入スクリプト
実行: python seed.py
"""
from database import SessionLocal, engine
from models import Base
import models
import crud

Base.metadata.create_all(bind=engine)
db = SessionLocal()

# ── 顧客 ──────────────────────────────────────────────────
customers = [
    {"name": "医療法人 さくら会", "category": "medical", "contact_name": "田中 一郎",
     "phone": "03-1234-5678", "email": "tanaka@sakurakai.jp", "address": "東京都千代田区1-1-1"},
    {"name": "国立医療センター", "category": "medical", "contact_name": "佐藤 花子",
     "phone": "03-9876-5432", "email": "sato@nmc.jp", "address": "東京都新宿区2-2-2"},
    {"name": "イタリア食材輸入商会", "category": "ham", "contact_name": "鈴木 太郎",
     "phone": "06-1111-2222", "email": "suzuki@itarya.co.jp", "address": "大阪府大阪市中央区3-3-3"},
    {"name": "レストラン ボルゴ", "category": "ham", "contact_name": "山田 次郎",
     "phone": "06-3333-4444", "email": "yamada@borgo.jp", "address": "大阪府梅田1-5-5"},
]
for c in customers:
    crud.create_customer(db, c)

# ── 商品 ──────────────────────────────────────────────────
products = [
    {"name": "血圧計 BP-500", "category": "medical", "sku": "MED-001",
     "unit_price": 45000, "unit": "台", "stock_alert_threshold": 3},
    {"name": "パルスオキシメーター OX-200", "category": "medical", "sku": "MED-002",
     "unit_price": 12000, "unit": "台", "stock_alert_threshold": 5},
    {"name": "体温計 TH-Pro", "category": "medical", "sku": "MED-003",
     "unit_price": 3500, "unit": "本", "stock_alert_threshold": 10},
    {"name": "プロシュート・ディ・パルマ 24ヶ月熟成", "category": "ham", "sku": "HAM-001",
     "unit_price": 25000, "unit": "本", "stock_alert_threshold": 2},
    {"name": "クラテッロ・ディ・ジベッロ", "category": "ham", "sku": "HAM-002",
     "unit_price": 38000, "unit": "本", "stock_alert_threshold": 2},
    {"name": "スペック・アルト・アディジェ", "category": "ham", "sku": "HAM-003",
     "unit_price": 18000, "unit": "kg", "stock_alert_threshold": 5},
]
for p in products:
    crud.create_product(db, p)

# ── 在庫 入庫 ─────────────────────────────────────────────
stock_data = [
    (1, 15, "初期入庫"),
    (2, 8, "初期入庫"),
    (3, 2, "初期入庫"),   # アラート確認用（閾値10以下）
    (4, 10, "初期入庫"),
    (5, 1, "初期入庫"),   # アラート確認用（閾値2以下）
    (6, 20, "初期入庫"),
]
for product_id, qty, reason in stock_data:
    crud.move_inventory(db, product_id, "in", qty, reason=reason)

# ── 見積 ──────────────────────────────────────────────────
from datetime import date, timedelta

crud.create_quote(db,
    customer_id=1,
    valid_until=date.today() + timedelta(days=30),
    notes="定期発注分",
    items=[
        {"product_id": 1, "quantity": 2},
        {"product_id": 2, "quantity": 5},
    ]
)

crud.create_quote(db,
    customer_id=3,
    valid_until=date.today() + timedelta(days=14),
    notes="秋の新商品ご提案",
    items=[
        {"product_id": 4, "quantity": 3},
        {"product_id": 6, "quantity": 10},
    ]
)

db.close()
print("✅ 初期データの投入が完了しました")
