from cryptography.fernet import Fernet, InvalidToken


def _fernet(key: str) -> Fernet:
    if not key:
        raise RuntimeError("PROVIDER_KEYS_ENCRYPTION_KEY is not configured.")
    try:
        return Fernet(key.encode("utf-8"))
    except (ValueError, TypeError) as exc:
        raise RuntimeError("PROVIDER_KEYS_ENCRYPTION_KEY must be a valid Fernet key.") from exc


def encrypt_secret(value: str, key: str) -> str:
    """Encrypt a provider credential before it is stored in the database."""
    if not value:
        raise ValueError("Cannot encrypt an empty secret.")
    return _fernet(key).encrypt(value.encode("utf-8")).decode("utf-8")


def decrypt_secret(token: str, key: str) -> str:
    try:
        return _fernet(key).decrypt(token.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise ValueError("The encrypted secret could not be authenticated.") from exc
