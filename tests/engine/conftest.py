from __future__ import annotations

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
)


@pytest.fixture(autouse=True)
def _seed_printpuf_env(monkeypatch: pytest.MonkeyPatch) -> None:
    private_key = Ed25519PrivateKey.generate()
    private_pem = private_key.private_bytes(
        encoding=Encoding.PEM,
        format=PrivateFormat.PKCS8,
        encryption_algorithm=NoEncryption(),
    ).decode("utf-8")
    public_pem = private_key.public_key().public_bytes(
        encoding=Encoding.PEM,
        format=PublicFormat.SubjectPublicKeyInfo,
    ).decode("utf-8")

    for env_name in (
        "PRINTPUF_ED25519_PRIVATE_KEY_PEM",
        "PRINTPUF_ED25519_PUBLIC_KEY_PEM",
        "PRINTPUF_PRIVATE_KEY_PEM",
        "PRINTPUF_PUBLIC_KEY_PEM",
    ):
        monkeypatch.setenv(env_name, private_pem if "PRIVATE" in env_name else public_pem)
