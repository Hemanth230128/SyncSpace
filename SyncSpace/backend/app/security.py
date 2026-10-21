import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
import bcrypt
import jwt

from app.config import settings


def hash_password(password: str) -> str:
    """
    Hashes a plaintext password using bcrypt with a securely generated salt.
    """
    password_bytes = password.encode("utf-8")
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password_bytes, salt)
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verifies a plaintext password against a stored bcrypt hash.
    Safe against timing attacks.
    """
    try:
        password_bytes = plain_password.encode("utf-8")
        hashed_bytes = hashed_password.encode("utf-8")
        return bcrypt.checkpw(password_bytes, hashed_bytes)
    except (ValueError, TypeError):
        return False


async def async_hash_password(password: str) -> str:
    """Non-blocking async version of hash_password."""
    return await asyncio.to_thread(hash_password, password)


async def async_verify_password(plain_password: str, hashed_password: str) -> bool:
    """Non-blocking async version of verify_password."""
    return await asyncio.to_thread(verify_password, plain_password, hashed_password)


def create_access_token(data: dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """
    Generates a signed JWT containing data payload and expiration timestamp.
    """
    to_encode = data.copy()
    now = datetime.now(timezone.utc)

    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode.update({"exp": expire, "iat": now})

    encoded_jwt = jwt.encode(
        to_encode,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )
    return encoded_jwt


def decode_access_token(token: str) -> Optional[dict[str, Any]]:
    """
    Decodes and validates a JWT access token signature and expiration.
    Returns payload dictionary if valid, or None if invalid or expired.
    """
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
        return payload
    except (jwt.PyJWTError, Exception):
        return None
