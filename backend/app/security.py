import hmac

from cryptography.fernet import Fernet


def verify_password(username: str, password: str, users: dict[str, str]) -> bool:
    expected = users.get(username)
    if expected is None:
        hmac.compare_digest(password, "")
        return False
    return hmac.compare_digest(password, expected)


class EncryptionService:
    def __init__(self, key: str):
        self._fernet = Fernet(key.encode("utf-8"))

    def encrypt(self, value: str) -> str:
        return self._fernet.encrypt(value.encode("utf-8")).decode("utf-8")

    def decrypt(self, value: str) -> str:
        return self._fernet.decrypt(value.encode("utf-8")).decode("utf-8")
