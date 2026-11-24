from argon2 import PasswordHasher
from argon2.exceptions import VerificationError

_password_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    if not password:
        raise ValueError("Password cannot be empty.")
    return _password_hasher.hash(password)


def verify_password(password: str, encoded_hash: str) -> bool:
    if not password or not encoded_hash:
        return False
    try:
        return _password_hasher.verify(encoded_hash, password)
    except VerificationError:
        return False
