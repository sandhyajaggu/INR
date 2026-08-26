import random
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

TokenType = Literal["access", "refresh"]


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, password_hash: str) -> bool:
    return pwd_context.verify(plain_password, password_hash)


def _create_token(subject: str, role: str, token_type: TokenType, expires_delta: timedelta) -> str:
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": subject,
        "role": role,
        "type": token_type,
        "iat": now,
        "exp": now + expires_delta,
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def create_access_token(staff_id: int, role: str) -> str:
    return _create_token(
        str(staff_id), role, "access", timedelta(minutes=settings.access_token_expire_minutes)
    )


def create_refresh_token(staff_id: int, role: str) -> str:
    return _create_token(
        str(staff_id), role, "refresh", timedelta(days=settings.refresh_token_expire_days)
    )


def decode_token(token: str) -> dict[str, Any] | None:
    try:
        return jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])
    except JWTError:
        return None


# --- Math CAPTCHA -----------------------------------------------------------
# /auth/captcha issues a short-lived signed token encoding the expected answer.
# /auth/login must submit that token back along with the user's answer; the
# server re-verifies the signature + expiry + answer server-side.


def generate_captcha() -> tuple[str, str, str]:
    """Returns (question, token). The token embeds the signed answer."""
    a, b = random.randint(1, 20), random.randint(1, 20)
    question = f"{a} + {b}"
    answer = str(a + b)
    now = datetime.now(timezone.utc)
    payload = {
        "answer": answer,
        "type": "captcha",
        "iat": now,
        "exp": now + timedelta(minutes=settings.captcha_token_expire_minutes),
    }
    token = jwt.encode(payload, settings.captcha_secret_key, algorithm=settings.jwt_algorithm)
    return question, token


def verify_captcha(token: str, submitted_answer: str) -> bool:
    try:
        payload = jwt.decode(token, settings.captcha_secret_key, algorithms=[settings.jwt_algorithm])
    except JWTError:
        return False
    if payload.get("type") != "captcha":
        return False
    return str(payload.get("answer")).strip() == submitted_answer.strip()
