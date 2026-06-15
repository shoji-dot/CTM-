import os
from datetime import datetime, timedelta
from utils import now_jst
import bcrypt as _bcrypt_lib
from itsdangerous import URLSafeTimedSerializer
from sqlalchemy.orm import Session
from models import Staff

# [C1] SECRET_KEY は必須環境変数。未設定時は起動を停止する。
SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError("環境変数 SECRET_KEY が未設定です。.env を確認してください。")
SESSION_MAX_AGE = 60 * 60 * 8  # 8時間

# passlib 1.7.4 + bcrypt 4.x の互換性バグを回避するため bcrypt を直接使用する。
# sha256_crypt ハッシュ（旧アルゴリズム）の検証のみ passlib を使用。
from passlib.context import CryptContext
_sha256_ctx = CryptContext(schemes=["sha256_crypt"])  # bcrypt バックエンドを使わない

serializer = URLSafeTimedSerializer(SECRET_KEY)


def hash_password(password: str) -> str:
    """bcrypt で新規ハッシュを生成する。"""
    return _bcrypt_lib.hashpw(password.encode("utf-8"), _bcrypt_lib.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    valid, _ = verify_and_update_password(plain, hashed)
    return valid


def verify_and_update_password(plain: str, hashed: str) -> tuple[bool, str | None]:
    """パスワード検証。
    - bcrypt ハッシュ ($2b$/$2a$) → bcrypt 直接検証
    - sha256_crypt ハッシュ ($5$) → passlib で検証後 bcrypt に再ハッシュ
    戻り値: (valid, new_hash_or_None)
    """
    if hashed.startswith("$2"):
        # bcrypt ハッシュ
        try:
            valid = _bcrypt_lib.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
        except Exception:
            valid = False
        return valid, None
    elif hashed.startswith("$5$"):
        # 旧 sha256_crypt ハッシュ → 検証後 bcrypt に移行
        try:
            valid = _sha256_ctx.verify(plain, hashed)
        except Exception:
            valid = False
        if valid:
            new_hash = hash_password(plain)
            return True, new_hash
        return False, None
    else:
        return False, None


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
    staff.last_active_at = now_jst()
    staff.last_active_page = page
    db.commit()


# ── [I1] CSRF保護 ─────────────────────────────────────────────────────────────────────────────
import hashlib, hmac, time

def generate_csrf_token(session_token: str) -> str:
    """セッショントークンと現在時刻(時間単位)からCSRFトークンを生成する。"""
    ts = str(int(time.time()) // 3600)  # 1時間単位で更新
    msg = f"{session_token}:{ts}".encode()
    return hmac.new(SECRET_KEY.encode(), msg, hashlib.sha256).hexdigest()

def verify_csrf_token(session_token: str, csrf_token: str) -> bool:
    """現在の時間帯 + 直前の時間帯の両方で検証（時間境界をまたぐ場合に対応）。"""
    if not csrf_token or not session_token:
        return False
    now = int(time.time()) // 3600
    for ts_offset in (0, -1):
        ts = str(now + ts_offset)
        msg = f"{session_token}:{ts}".encode()
        expected = hmac.new(SECRET_KEY.encode(), msg, hashlib.sha256).hexdigest()
        if hmac.compare_digest(expected, csrf_token):
            return True
    return False
