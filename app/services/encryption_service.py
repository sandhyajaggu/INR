from cryptography.fernet import Fernet

from app.core.config import settings

_fernet = Fernet(settings.aadhaar_encryption_key.encode())


def encrypt_aadhaar(plain_aadhaar: str) -> str:
    return _fernet.encrypt(plain_aadhaar.encode()).decode()


def decrypt_aadhaar(encrypted_aadhaar: str) -> str:
    return _fernet.decrypt(encrypted_aadhaar.encode()).decode()


def mask_aadhaar(encrypted_aadhaar: str | None) -> str | None:
    """Never decrypt for a normal response — return a masked placeholder instead."""
    if not encrypted_aadhaar:
        return None
    try:
        plain = decrypt_aadhaar(encrypted_aadhaar)
    except Exception:
        return "XXXX-XXXX-XXXX"
    if len(plain) <= 4:
        return "X" * len(plain)
    return "X" * (len(plain) - 4) + plain[-4:]
