from __future__ import annotations

import cbor2
import pytest
from cryptography.exceptions import InvalidSignature

from engine.signer import sign_payload, verify_payload
from scripts.manual_artifacts import save_bytes


def test_sign_payload_returns_cbor_bytes() -> None:
    signed = sign_payload("product-test-1", "vendor-abc")

    decoded = cbor2.loads(signed)
    assert isinstance(signed, bytes)
    assert decoded["pid"] == "product-test-1"
    assert decoded["vid"] == "vendor-abc"
    assert "sketch" not in decoded
    assert isinstance(decoded["sig"], bytes)
    assert len(decoded["sig"]) == 64


def test_verify_payload_returns_decoded_dict() -> None:
    signed = sign_payload("product-test-1", None)

    verified = verify_payload(signed)

    assert verified["pid"] == "product-test-1"
    assert verified["vid"] is None
    assert "sketch" not in verified


def test_verify_payload_accepts_legacy_sketch_payload() -> None:
    signed = sign_payload("product-test-1", "vendor-abc", b"\x02" * 32)

    verified = verify_payload(signed)

    assert verified["pid"] == "product-test-1"
    assert verified["vid"] == "vendor-abc"
    assert verified["sketch"] == b"\x02" * 32


def test_verify_payload_rejects_tampering() -> None:
    signed = sign_payload("product-test-1", "vendor-abc")
    tampered = cbor2.loads(signed)
    tampered["pid"] = "product-999"
    tampered_bytes = cbor2.dumps(tampered)

    with pytest.raises(InvalidSignature):
        verify_payload(tampered_bytes)


def test_signer_output_can_be_saved_for_manual_inspection() -> None:
    signed = sign_payload("product-test-1", "vendor-abc")

    output_path = save_bytes(signed, "signer-stage2-test.cbor")

    assert output_path.exists()
    assert output_path.read_bytes() == signed
