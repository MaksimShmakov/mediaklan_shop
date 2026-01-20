from typing import Optional

from passlib.context import CryptContext  # noqa: F401

pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")


def validate_password(password: str) -> Optional[str]:
    cleaned = password.strip()
    if not cleaned or len(cleaned) < 6:
        return "Пароль должен быть не короче 6 символов"
    if len(cleaned) > 128:
        return "Пароль должен быть не длиннее 128 символов"
    return None


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)
