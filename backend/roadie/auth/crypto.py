"""Cifra simétrica para segredos guardados no banco (ex.: chave da OpenAI).

A chave de cifra deriva de SECRET_KEY, então quem tem o banco mas não tem o
.env não lê o segredo. Se SECRET_KEY mudar, o valor guardado deixa de ser
legível e o sistema pede a chave de novo, em vez de falhar silenciosamente.
"""

from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from roadie.config import get_settings


class CryptoError(Exception):
    pass


def _fernet() -> Fernet:
    secret = get_settings().secret_key.encode("utf-8")
    derived = hashlib.sha256(b"roadie-settings:" + secret).digest()
    return Fernet(base64.urlsafe_b64encode(derived))


def encrypt(plain: str) -> str:
    return _fernet().encrypt(plain.encode("utf-8")).decode("ascii")


def decrypt(token: str) -> str:
    try:
        return _fernet().decrypt(token.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError) as exc:
        raise CryptoError(
            "não foi possível decifrar o valor guardado; a SECRET_KEY mudou?"
        ) from exc
