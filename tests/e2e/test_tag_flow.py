from __future__ import annotations

import base64
from types import SimpleNamespace

import pytest

from core.engine_contract import VerificationResult


@pytest.fixture
def brand_token(client) -> str:
    response = client.post(
        "/api/auth/signup",
        json={
            "full_name": "Brand Owner",
            "email": "brand@example.com",
            "password": "secretpass123",
            "role": "brand",
        },
    )
    assert response.status_code == 201
    return response.json()["access_token"]


def test_tag_generate_list_and_verify_flow(client, brand_token: str, monkeypatch: pytest.MonkeyPatch) -> None:
    from api import tags as tags_module

    async def _fake_verify_transaction(_transaction_ref: str, _expected_amount: int):
        return True

    async def _fake_generate_tag(*, product_id: str, vendor_id: str | None = None):
        return SimpleNamespace(product_id=product_id, qr_png_bytes=b"qr-bytes")

    async def _fake_verify_tag(*, image_bytes: bytes, product_id: str, enrolment_bundle=None):
        return VerificationResult(score=0.91, verdict="AUTHENTIC")

    monkeypatch.setattr(tags_module, "verify_squad_transaction", _fake_verify_transaction)
    monkeypatch.setattr(tags_module.engine, "generate_tag", _fake_generate_tag)
    monkeypatch.setattr(tags_module.engine, "verify_tag", _fake_verify_tag)

    generate_response = client.post(
        "/api/tags/generate",
        data={
            "transaction_ref": "txn-123",
            "product_type": "Sneakers",
            "vendor_id": "vendor-9",
        },
        headers={"Authorization": f"Bearer {brand_token}"},
    )

    assert generate_response.status_code == 200
    generate_body = generate_response.json()
    assert generate_body["status"] == "generated"
    assert generate_body["vendor_id"] == "vendor-9"
    assert generate_body["qr_png_b64"] == base64.b64encode(b"qr-bytes").decode("ascii")

    list_response = client.get(
        "/api/tags/list",
        headers={"Authorization": f"Bearer {brand_token}"},
    )

    assert list_response.status_code == 200
    list_body = list_response.json()
    assert len(list_body["tags"]) == 1
    assert list_body["tags"][0]["transaction_ref"] == "txn-123"

    product_id = generate_body["product_id"]
    verify_response = client.post(
        "/api/tags/verify",
        data={"product_id": product_id, "device_hash": "device-123"},
        files={"image": ("scan.jpg", b"scan-bytes", "image/jpeg")},
    )

    assert verify_response.status_code == 200
    verify_body = verify_response.json()
    assert verify_body["product_id"] == product_id
    assert verify_body["verdict"] == "AUTHENTIC"
    assert verify_body["score"] == 0.91
