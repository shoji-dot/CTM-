"""
認証ユニットテスト

対象: auth.py の各関数
  - hash_password / verify_password
  - create_session_token / decode_session_token（有効・期限切れ）
  - generate_csrf_token / verify_csrf_token
"""

import pytest
from auth import (
    hash_password,
    verify_password,
    create_session_token,
    decode_session_token,
    generate_csrf_token,
    verify_csrf_token,
)


class TestPassword:
    def test_hash_is_not_plain(self):
        hashed = hash_password("secret")
        assert hashed != "secret"

    def test_verify_correct_password(self):
        hashed = hash_password("mypassword")
        assert verify_password("mypassword", hashed) is True

    def test_verify_wrong_password(self):
        hashed = hash_password("mypassword")
        assert verify_password("wrongpassword", hashed) is False

    def test_hash_is_deterministic_with_same_input(self):
        # 同じパスワードでも毎回異なるハッシュ（salt付き）
        h1 = hash_password("same")
        h2 = hash_password("same")
        assert verify_password("same", h1)
        assert verify_password("same", h2)


class TestSessionToken:
    def test_encode_decode_roundtrip(self):
        token = create_session_token(42)
        staff_id = decode_session_token(token)
        assert staff_id == 42

    def test_invalid_token_returns_none(self):
        assert decode_session_token("invalid-token") is None

    def test_empty_token_returns_none(self):
        assert decode_session_token("") is None

    def test_tampered_token_returns_none(self):
        token = create_session_token(1)
        tampered = token[:-5] + "XXXXX"
        assert decode_session_token(tampered) is None


class TestCsrfToken:
    def test_valid_token_accepted(self):
        session = create_session_token(1)
        csrf = generate_csrf_token(session)
        assert verify_csrf_token(session, csrf) is True

    def test_wrong_session_rejected(self):
        session_a = create_session_token(1)
        session_b = create_session_token(2)
        csrf = generate_csrf_token(session_a)
        assert verify_csrf_token(session_b, csrf) is False

    def test_empty_token_rejected(self):
        session = create_session_token(1)
        assert verify_csrf_token(session, "") is False

    def test_empty_session_rejected(self):
        session = create_session_token(1)
        csrf = generate_csrf_token(session)
        assert verify_csrf_token("", csrf) is False

    def test_tampered_csrf_rejected(self):
        session = create_session_token(1)
        csrf = generate_csrf_token(session)
        assert verify_csrf_token(session, csrf[:-4] + "XXXX") is False
