from __future__ import annotations

import asyncio
import base64
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from core.auth import get_current_user
from core.database import get_db_session
from core.engine_contract import VerificationResult
from main import app
from models.product import Product
from models.user import User, UserRole


class FakeResult:
    def __init__(self, rows: list[object]):
        self._rows = rows

    def first(self):
        return self._rows[0] if self._rows else None

    def all(self):
        return self._rows


class FakeSession:
    def __init__(self, *, exec_results: list[list[object] | None] | None = None, get_result: object | None = None):
        self.exec_results = list(exec_results or [])
        self.get_result = get_result
        self.added: list[object] = []
        self.commits = 0
        self.refreshed: list[object] = []

    async def exec(self, _statement):
        rows = self.exec_results.pop(0) if self.exec_results else []
        return FakeResult(rows or [])

    async def get(self, _model, _key):
        return self.get_result

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.commits += 1

    async def refresh(self, obj):
        self.refreshed.append(obj)


@pytest.fixture(autouse=True)
def _reset_dependency_overrides():
    original = dict(app.dependency_overrides)
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()
    app.dependency_overrides.update(original)


def _client_for(*, user: User | None = None, session: FakeSession | None = None) -> tuple[TestClient, FakeSession]:
    test_session = session or FakeSession()
    current_user = user or User(id="brand-1", email="brand@example.test", role=UserRole.BRAND)

    async def _override_session():
        yield test_session

    def _override_user():
        return current_user

    app.dependency_overrides[get_db_session] = _override_session
    app.dependency_overrides[get_current_user] = _override_user
    return TestClient(app), test_session


def test_generate_tag_creates_product_and_returns_qr(monkeypatch: pytest.MonkeyPatch) -> None:
    from api import tags as tags_module

    async def _fake_verify_transaction(_transaction_ref: str, _expected_amount: int):
        return True

    async def _fake_generate_tag(*, product_id: str, vendor_id: str | None = None):
        return SimpleNamespace(product_id=product_id, qr_png_bytes=b"qr-bytes")

    upload_calls: list[tuple[str, bytes]] = []

    monkeypatch.setattr(tags_module, "verify_squad_transaction", _fake_verify_transaction)
    monkeypatch.setattr(tags_module.engine, "generate_tag", _fake_generate_tag)
    monkeypatch.setattr(tags_module, "download_qr_png", lambda product_id: None)
    monkeypatch.setattr(
        tags_module,
        "upload_qr_png",
        lambda product_id, png_bytes: upload_calls.append((product_id, png_bytes)),
    )

    client, session = _client_for()
    response = client.post(
        "/api/tags/generate",
        data={"transaction_ref": "txn-123", "product_type": "Sneakers", "vendor_id": "vendor-9"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["transaction_ref"] == "txn-123"
    assert body["product_type"] == "Sneakers"
    assert body["vendor_id"] == "vendor-9"
    assert body["status"] == "generated"
    assert body["qr_png_b64"] == base64.b64encode(b"qr-bytes").decode("ascii")
    assert session.added
    product = session.added[0]
    assert product.status == "generated"
    assert product.transaction_ref == "txn-123"
    assert upload_calls == [(body["product_id"], b"qr-bytes")]


def test_generate_tag_rejects_unknown_vendor_id(monkeypatch: pytest.MonkeyPatch) -> None:
    from api import tags as tags_module

    async def _fake_verify_transaction(_transaction_ref: str, _expected_amount: int):
        return True

    async def _unexpected_generate_tag(*_args, **_kwargs):
        pytest.fail("engine.generate_tag should not be called when vendor_id is invalid")

    monkeypatch.setattr(tags_module, "verify_squad_transaction", _fake_verify_transaction)
    monkeypatch.setattr(tags_module.engine, "generate_tag", _unexpected_generate_tag)

    client, session = _client_for(session=FakeSession(exec_results=[[], []]))
    response = client.post(
        "/api/tags/generate",
        data={"transaction_ref": "txn-123", "product_type": "Sneakers", "vendor_id": "vendor-9"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Vendor 'vendor-9' not found."
    assert session.added == []


def test_enrol_tag_persists_bundle_and_updated_qr(monkeypatch: pytest.MonkeyPatch) -> None:
    from api import tags as tags_module

    product = Product(
        id="product-1",
        brand_id="brand-1",
        vendor_id="vendor-9",
        product_type="Sneakers",
        transaction_ref="txn-123",
        status="generated",
        qr_png_b64="initial",
    )

    async def _fake_enrol_tag(*, image_source, product_id: str, vendor_id: str | None = None, required_scan_count: int = 3):
        return SimpleNamespace(updated_qr_png_bytes=b"updated-qr", scan_count=3)

    monkeypatch.setattr(tags_module.engine, "enrol_tag", _fake_enrol_tag)
    monkeypatch.setattr(tags_module, "serialize_enrolment_bundle", lambda enrolment_result, vendor_id=None: {"product_id": "product-1", "vendor_id": vendor_id})
    monkeypatch.setattr(tags_module, "download_qr_png", lambda product_id: None)
    upload_calls: list[tuple[str, bytes]] = []
    monkeypatch.setattr(
        tags_module,
        "upload_qr_png",
        lambda product_id, png_bytes: upload_calls.append((product_id, png_bytes)),
    )

    client, session = _client_for(session=FakeSession(get_result=product))
    response = client.post(
        "/api/tags/enrol",
        data={"product_id": "product-1"},
        files=[
            ("images", ("scan-1.jpg", b"scan-1", "image/jpeg")),
            ("images", ("scan-2.jpg", b"scan-2", "image/jpeg")),
            ("images", ("scan-3.jpg", b"scan-3", "image/jpeg")),
        ],
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "enrolled"
    assert body["enrolment_scan_count"] == 3
    assert body["qr_png_b64"] == base64.b64encode(b"updated-qr").decode("ascii")
    assert product.status == "enrolled"
    assert product.enrolment_bundle == {"product_id": "product-1", "vendor_id": "vendor-9"}
    assert session.commits == 1
    assert upload_calls == [("product-1", b"updated-qr")]


def test_generate_tag_prefers_spaces_when_cache_is_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    from api import tags as tags_module

    async def _fake_verify_transaction(_transaction_ref: str, _expected_amount: int):
        return True

    async def _fake_generate_tag(*, product_id: str, vendor_id: str | None = None):
        return SimpleNamespace(product_id=product_id, qr_png_bytes=b"qr-bytes")

    monkeypatch.setattr(tags_module, "verify_squad_transaction", _fake_verify_transaction)
    monkeypatch.setattr(tags_module.engine, "generate_tag", _fake_generate_tag)
    monkeypatch.setattr(tags_module, "upload_qr_png", lambda product_id, png_bytes: None)
    monkeypatch.setattr(tags_module, "download_qr_png", lambda product_id: b"remote-bytes")

    client, _ = _client_for()
    response = client.post(
        "/api/tags/generate",
        data={"transaction_ref": "txn-456", "product_type": "Hoodie"},
    )

    assert response.status_code == 200
    assert response.json()["qr_png_b64"] == base64.b64encode(b"remote-bytes").decode("ascii")


def test_enrol_tag_returns_400_for_product_id_mismatch(monkeypatch: pytest.MonkeyPatch) -> None:
    from api import tags as tags_module

    product = Product(
        id="0f6e5c55fa0c4e2bbb6cd1933d9cfe5a",
        brand_id="brand-1",
        vendor_id="vendor-9",
        product_type="PEM",
        transaction_ref="txn-123",
        status="generated",
        qr_png_b64="initial",
    )

    async def _fake_enrol_tag(*, image_source, product_id: str, vendor_id: str | None = None, required_scan_count: int = 3):
        raise ValueError(
            "enrolment image payload product_id 'product-123' does not match "
            "'0f6e5c55fa0c4e2bbb6cd1933d9cfe5a'"
        )

    monkeypatch.setattr(tags_module.engine, "enrol_tag", _fake_enrol_tag)

    client, session = _client_for(session=FakeSession(get_result=product))
    response = client.post(
        "/api/tags/enrol",
        data={"product_id": product.id},
        files=[
            ("images", ("scan-1.jpg", b"scan-1", "image/jpeg")),
            ("images", ("scan-2.jpg", b"scan-2", "image/jpeg")),
            ("images", ("scan-3.jpg", b"scan-3", "image/jpeg")),
        ],
    )

    assert response.status_code == 400
    assert "different tag" in response.json()["detail"]
    assert session.commits == 0


def test_list_tags_returns_brand_products() -> None:
    product_one = Product(
        id="product-1",
        brand_id="brand-1",
        vendor_id="vendor-9",
        product_type="Sneakers",
        transaction_ref="txn-1",
        status="enrolled",
        enrolment_scan_count=3,
    )
    product_two = Product(
        id="product-2",
        brand_id="brand-1",
        vendor_id=None,
        product_type="Handbag",
        transaction_ref="txn-2",
        status="generated",
        enrolment_scan_count=0,
    )

    client, _ = _client_for(session=FakeSession(exec_results=[[product_one, product_two]]))
    response = client.get("/api/tags/list")

    assert response.status_code == 200
    body = response.json()
    assert [item["product_id"] for item in body["tags"]] == ["product-1", "product-2"]
    assert body["tags"][0]["status"] == "enrolled"
    assert body["tags"][1]["status"] == "generated"


@pytest.mark.parametrize(
    ("backend_verdict", "report_url"),
    [
        ("AUTHENTIC", None),
        ("SUSPICIOUS", None),
        ("FAKE", "https://wa.me/?text=FAKE%20product%20detected%20(ID%3A%20product-1).%20Report%20to%20NAFDAC."),
    ],
)
def test_verify_tag_returns_backend_verdicts(monkeypatch: pytest.MonkeyPatch, backend_verdict: str, report_url: str | None) -> None:
    from api import tags as tags_module

    product = Product(
        id="product-1",
        brand_id="brand-1",
        vendor_id=None,
        product_type="Sneakers",
        transaction_ref="txn-1",
        status="enrolled",
        enrolment_bundle={"product_id": "product-1"},
    )

    async def _fake_verify_tag(*, image_bytes: bytes, product_id: str, enrolment_bundle=None):
        return VerificationResult(score=0.91, verdict=backend_verdict)

    monkeypatch.setattr(tags_module.engine, "verify_tag", _fake_verify_tag)

    client, session = _client_for(session=FakeSession(get_result=product))
    response = client.post(
        "/api/tags/verify",
        data={"product_id": "product-1", "device_hash": "device-123"},
        files={"image": ("scan.jpg", b"scan-bytes", "image/jpeg")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["product_id"] == "product-1"
    assert body["verdict"] == backend_verdict
    assert body["score"] == 0.91
    assert body["report_url"] == report_url
    assert body["product"]["product_name"] == "product-1"
    assert session.commits == 1


def test_openapi_exposes_tag_routes_and_not_batch() -> None:
    paths = app.openapi()["paths"]

    assert "/api/tags/generate" in paths
    assert "/api/tags/enrol" in paths
    assert "/api/tags/list" in paths
    assert "/api/tags/verify" in paths
    assert all(not path.startswith("/api/batch") for path in paths)
