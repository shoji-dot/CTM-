from datetime import datetime, timedelta
from passlib.context import CryptContext
from itsdangerous import URLSafeTimedSerializer
from sqlalchemy.orm import Session
from models import Staff

SECRET_KEY = "salescore-secret-key-2026"
SESSION_MAX_AGE = 60 * 60 * 8  # 8時間

pwd_context = CryptContext(schemes=["sha256_crypt"], deprecated="auto")
serializer = URLSafeTimedSerializer(SECRET_KEY)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_session_token(staff_id: int) -> str:
    return serializer.dumps({"staff_id": staff_id})


def decode_session_token(token: str):
    try:
        data = serializer.loads(token, max_age=SESSION_MAX_AGE)
        return data.get("staff_id")
    except Exception:
        return None


def get_current_staff(token: str, db: Session):
    if not token:
        return None
    staff_id = decode_session_token(token)
    if not staff_id:
        return None
    staff = db.query(Staff).filter(Staff.id == staff_id, Staff.is_active == True).first()
    return staff


def update_last_active(staff: Staff, page: str, db: Session):
    staff.last_active_at = datetime.utcnow() + timedelta(hours=9)
    staff.last_active_page = page
    db.commit()
