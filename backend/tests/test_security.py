from cryptography.fernet import Fernet

from app.core.crypto import decrypt_secret, encrypt_secret
from app.core.security import hash_password, verify_password


def test_password_hash_uses_argon2id() -> None:
    password = "Correct Horse Battery Staple 42!"
    encoded = hash_password(password)

    assert encoded != password
    assert encoded.startswith("$argon2id$")
    assert verify_password(password, encoded)
    assert not verify_password("wrong password", encoded)


def test_provider_secret_encryption_round_trip() -> None:
    key = Fernet.generate_key().decode("utf-8")
    secret = "provider-secret-for-test-only"

    encrypted = encrypt_secret(secret, key)

    assert encrypted != secret
    assert decrypt_secret(encrypted, key) == secret
