from __future__ import annotations

import os
from functools import lru_cache

import cbor2
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from dotenv import load_dotenv


PRIVATE_KEY_ENV_VARS = (
    "PRINTPUF_ED25519_PRIVATE_KEY_PEM",
    "PRINTPUF_PRIVATE_KEY_PEM",
)
PUBLIC_KEY_ENV_VARS = (
    "PRINTPUF_ED25519_PUBLIC_KEY_PEM",
    "PRINTPUF_PUBLIC_KEY_PEM",
)


@lru_cache(maxsize=1)
def _load_environment() -> None:
    load_dotenv()


def _get_env_value(*names: str) -> str:
    _load_environment()
    for name in names:
        value = os.getenv(name)
        if value:
            return value.strip()
    if len(names) == 1:
        raise ValueError(f"{names[0]} is not set")
    raise ValueError(f"Set one of: {', '.join(names)}")


def load_private_key_pem_from_env() -> bytes:
    return _get_env_value(*PRIVATE_KEY_ENV_VARS).encode("utf-8")


def load_public_key_pem_from_env() -> bytes:
    return _get_env_value(*PUBLIC_KEY_ENV_VARS).encode("utf-8")


def load_keypair_from_env() -> tuple[bytes, bytes]:
    return load_private_key_pem_from_env(), load_public_key_pem_from_env()


def _load_private_key(private_key_pem: bytes) -> Ed25519PrivateKey:
    key = serialization.load_pem_private_key(private_key_pem, password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise TypeError("private_key_pem does not contain an Ed25519 private key")
    return key


def _load_public_key(public_key_pem: bytes) -> Ed25519PublicKey:
    key = serialization.load_pem_public_key(public_key_pem)
    if not isinstance(key, Ed25519PublicKey):
        raise TypeError("public_key_pem does not contain an Ed25519 public key")
    return key


def _resolve_private_key_pem(private_key_pem: bytes | None) -> bytes:
    if private_key_pem is None:
        return load_private_key_pem_from_env()
    if not isinstance(private_key_pem, bytes) or not private_key_pem:
        raise ValueError("private_key_pem must be non-empty bytes")
    return private_key_pem


def _resolve_public_key_pem(public_key_pem: bytes | None) -> bytes:
    if public_key_pem is None:
        return load_public_key_pem_from_env()
    if not isinstance(public_key_pem, bytes) or not public_key_pem:
        raise ValueError("public_key_pem must be non-empty bytes")
    return public_key_pem


def _build_message(product_id: str, vendor_id: str | None, lbp_sketch: bytes) -> bytes:
    return product_id.encode() + (vendor_id or "").encode() + lbp_sketch


def sign_payload(
    product_id: str,
    vendor_id: str | None,
    lbp_sketch: bytes,
    private_key_pem: bytes | None = None,
) -> bytes:
    if not product_id:
        raise ValueError("product_id must be a non-empty string")
    if not isinstance(lbp_sketch, bytes) or len(lbp_sketch) != 32:
        raise ValueError("lbp_sketch must be exactly 32 bytes")

    private_key = _load_private_key(_resolve_private_key_pem(private_key_pem))
    message = _build_message(product_id, vendor_id, lbp_sketch)
    signature = private_key.sign(message)

    payload = {
        "pid": product_id,
        "vid": vendor_id,
        "sketch": lbp_sketch,
        "sig": signature,
    }
    return cbor2.dumps(payload)


def verify_payload(cbor_bytes: bytes, public_key_pem: bytes | None = None) -> dict:
    if not isinstance(cbor_bytes, bytes) or not cbor_bytes:
        raise ValueError("cbor_bytes must be non-empty bytes")

    payload = cbor2.loads(cbor_bytes)
    message = _build_message(payload["pid"], payload["vid"], payload["sketch"])

    public_key = _load_public_key(_resolve_public_key_pem(public_key_pem))
    public_key.verify(payload["sig"], message)
    return payload
