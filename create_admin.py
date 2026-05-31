from database import SessionLocal, engine
from models import Base, Staff
from auth import hash_password

Base.metadata.create_all(bind=engine)
db = SessionLocal()

existing = db.query(Staff).filter(Staff.login_id == "284").first()
if not existing:
    admin = Staff(
        name="管理者",
        login_id="284",
        password_hash=hash_password("284"),
        role="admin",
        department="管理部",
    )
    db.add(admin)
    db.commit()
    print("✅ 管理者アカウントを作成しました")
    print("   ログインID: 284")
    print("   パスワード: 284")
else:
    print("ℹ 管理者アカウントはすでに存在します")
db.close()
