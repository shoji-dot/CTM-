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

# パスワードアルゴリズム優先順位（新→旧）:
#   argon2id  ($argon2id$) … 新規ハッシュ（現行）
#   bcrypt    ($2b$/$2a$)  … 旧ハッシュ、ログイン時に argon2 へ自動移行
#   sha256_crypt ($5$)     … 最旧ハッシュ、ログイン時に argon2 へ自動移行
from argon2 import PasswordHasher as _ArgonHasher
from argon2.exceptions import VerifyMismatchError as _ArgonMismatch, VerificationError as _ArgonVerifyErr
from passlib.context import CryptContext
_argon = _ArgonHasher()  # デフォルト: argon2id, m=65536, t=3, p=4
_sha256_ctx = CryptContext(schemes=["sha256_crypt"])

serializer = URLSafeTimedSerializer(SECRET_KEY)


def hash_password(password: str) -> str:
    """argon2id で新規ハッシュを生成する。"""
    return _argon.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    valid, _ = verify_and_update_password(plain, hashed)
    return valid


def verify_and_update_password(plain: str, hashed: str) -> tuple[bool, str | None]:
    """パスワード検証。アルゴリズムを自動判定し、旧形式は argon2 へ自動移行する。
    - argon2id ($argon2id$) → argon2 検証（現行）
    - bcrypt   ($2b$/$2a$)  → bcrypt 検証 → argon2 に再ハッシュ
    - sha256_crypt ($5$)    → passlib 検証 → argon2 に再ハッシュ
    戻り値: (valid, new_hash_or_None)  new_hash は移行時のみ返す
    """
    if hashed.startswith("$argon2"):
        # argon2 ハッシュ（現行）
        try:
            _argon.verify(hashed, plain)
            # パラメータが古い場合は再ハッシュ（argon2-cffi の needs_rehash 機能）
            new_hash = hash_password(plain) if _argon.check_needs_rehash(hashed) else None
            return True, new_hash
        except (_ArgonMismatch, _ArgonVerifyErr):
            return False, None
        except Exception:
            return False, None
    elif hashed.startswith("$2"):
        # bcrypt ハッシュ → 検証後 argon2 へ移行
        try:
            valid = _bcrypt_lib.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
        except Exception:
            valid = False
        if valid:
            return True, hash_password(plain)
        return False, None
    elif hashed.startswith("$5$"):
        # 旧 sha256_crypt ハッシュ → 検証後 argon2 へ移行
        try:
            valid = _sha256_ctx.verify(plain, hashed)
        except Exception:
            valid = False
        if valid:
            return True, hash_password(plain)
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
