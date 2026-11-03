"""Primitivas de segurança.

- Senhas: Argon2id (argon2-cffi), com re-hash transparente quando os parâmetros mudam.
- Acesso: JWT HS256 de curta duração, assinado com SECRET_KEY.
- Refresh: token aleatório opaco; só o hash SHA-256 vai para o banco, com
  expiração e revogação (rotação a cada uso).
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from roadie.config import get_settings

_hasher = PasswordHasher()
ACCESS_COOKIE = "roadie_access"
REFRESH_COOKIE = "roadie_refresh"
MIN_PASSWORD_LENGTH = 10


class AuthError(Exception):
    pass


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)


def validate_password_strength(password: str) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise AuthError(f"a senha precisa ter pelo menos {MIN_PASSWORD_LENGTH} caracteres")
    if (
        password.lower() == password
        or password.upper() == password
        or not any(c.isdigit() for c in password)
    ):
        raise AuthError("a senha precisa misturar letras maiúsculas, minúsculas e números")


def create_access_token(user_id: uuid.UUID, role: str, minutes: int | None = None) -> str:
    s = get_settings()
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=minutes or s.access_token_minutes)).timestamp()),
        "typ": "access",
    }
    return jwt.encode(payload, s.secret_key, algorithm="HS256")


def decode_access_token(token: str) -> dict:
    s = get_settings()
    try:
        payload = jwt.decode(token, s.secret_key, algorithms=["HS256"])
    except jwt.ExpiredSignatureError as exc:
        raise AuthError("sessão expirada") from exc
    except jwt.InvalidTokenError as exc:
        raise AuthError("token inválido") from exc
    if payload.get("typ") != "access":
        raise AuthError("token inválido")
    return payload


def new_refresh_token() -> tuple[str, str, datetime]:
    """Retorna (token em claro, hash para o banco, expiração)."""
    s = get_settings()
    raw = secrets.token_urlsafe(48)
    return raw, hash_refresh_token(raw), datetime.now(UTC) + timedelta(days=s.refresh_token_days)


def hash_refresh_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
