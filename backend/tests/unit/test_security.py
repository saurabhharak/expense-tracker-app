import uuid
from datetime import datetime, timedelta, timezone

import pytest
from jose import JWTError

from app.core.security import create_access_token, decode_access_token, generate_refresh_token, hash_refresh_token


class TestCreateAccessToken:
    def test_returns_string(self, rsa_keys):
        token = create_access_token(user_id=uuid.uuid4())
        assert isinstance(token, str)
        assert len(token) > 0

    def test_contains_expected_claims(self, rsa_keys):
        user_id = uuid.uuid4()
        token = create_access_token(user_id=user_id, email="test@example.com")
        payload = decode_access_token(token)
        assert payload["sub"] == str(user_id)
        assert payload["email"] == "test@example.com"
        assert payload["type"] == "access"
        assert "iat" in payload
        assert "exp" in payload

    def test_omits_email_when_none(self, rsa_keys):
        token = create_access_token(user_id=uuid.uuid4())
        payload = decode_access_token(token)
        assert "email" not in payload


class TestDecodeAccessToken:
    def test_rejects_expired_token(self, rsa_keys, monkeypatch):
        # Use -1 minute so the token exp is 1 minute in the past; jose does not
        # reject tokens with exp == now (no leeway), only strictly past exp values.
        monkeypatch.setattr("app.core.config.settings.ACCESS_TOKEN_EXPIRE_MINUTES", -1)
        token = create_access_token(user_id=uuid.uuid4())
        with pytest.raises(JWTError):
            decode_access_token(token)

    def test_rejects_garbage_token(self, rsa_keys):
        with pytest.raises(JWTError):
            decode_access_token("not.a.valid.jwt")

    def test_rejects_token_signed_with_different_key(self, rsa_keys, tmp_path, monkeypatch):
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import rsa as rsa_mod

        token = create_access_token(user_id=uuid.uuid4())

        other_key = rsa_mod.generate_private_key(public_exponent=65537, key_size=2048)
        other_pub = other_key.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        other_pub_path = tmp_path / "other_public.pem"
        other_pub_path.write_bytes(other_pub)
        monkeypatch.setattr("app.core.config.settings.JWT_PUBLIC_KEY_PATH", str(other_pub_path))

        with pytest.raises(JWTError):
            decode_access_token(token)


class TestRefreshToken:
    def test_generate_returns_64_char_hex(self):
        token = generate_refresh_token()
        assert len(token) == 64
        assert all(c in "0123456789abcdef" for c in token)

    def test_generate_unique(self):
        t1 = generate_refresh_token()
        t2 = generate_refresh_token()
        assert t1 != t2

    def test_hash_is_deterministic(self):
        token = "a" * 64
        h1 = hash_refresh_token(token)
        h2 = hash_refresh_token(token)
        assert h1 == h2

    def test_hash_is_hex_sha256(self):
        token = "test"
        h = hash_refresh_token(token)
        assert len(h) == 64  # SHA-256 produces 64 hex chars
