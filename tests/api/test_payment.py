from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from core.database import get_db_session
from core.security import create_access_token
from main import app
from models.user import User, UserRole


class FakeResult:
    def __init__(self, rows: list[object]):
        self._rows = rows

    def first(self):
        return self._rows[0] if self._rows else None


class FakeSession:
    def __init__(self, *, exec_results: list[list[object] | None] | None = None):
        self.exec_results = list(exec_results or [])

    async def exec(self, _statement):
        rows = self.exec_results.pop(0) if self.exec_results else []
        return FakeResult(rows or [])


@pytest.fixture(autouse=True)
def _reset_dependency_overrides():
    original = dict(app.dependency_overrides)
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()
    app.dependency_overrides.update(original)


def _client_for(session: FakeSession) -> TestClient:
    async def _override_session():
        yield session

    app.dependency_overrides[get_db_session] = _override_session
    return TestClient(app)


def test_initiate_tag_payment_returns_checkout_url_and_reference(monkeypatch: pytest.MonkeyPatch) -> None:
    from api import tags as tags_module

    user = User(
        id="brand-1",
        full_name="Brand Owner",
        email="brand@example.test",
        role=UserRole.BRAND,
    )
    session = FakeSession(exec_results=[[user]])
    client = _client_for(session)

    async def _fake_initiate_squad_transaction(**kwargs):
        return {
            "transaction_ref": "SQ-123",
            "checkout_url": "https://checkout.example.test",
            "amount": 150,
        }

    monkeypatch.setattr(tags_module, "initiate_squad_transaction", _fake_initiate_squad_transaction)

    response = client.post(
        "/api/tags/payment/initiate",
        headers={"Authorization": f"Bearer {create_access_token(subject='brand-1')}"},
        json={"product_type": "Sneakers", "vendor_id": "vendor-9"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["transaction_ref"] == "SQ-123"
    assert body["checkout_url"] == "https://checkout.example.test"
    assert body["amount"] == 150


def test_initiate_tag_payment_rejects_unknown_vendor_id(monkeypatch: pytest.MonkeyPatch) -> None:
    from api import tags as tags_module

    session = FakeSession(exec_results=[[]])
    client = _client_for(session)

    async def _unexpected_initiate_squad_transaction(**kwargs):
        pytest.fail("initiate_squad_transaction should not be called when vendor_id is invalid")

    monkeypatch.setattr(tags_module, "initiate_squad_transaction", _unexpected_initiate_squad_transaction)

    response = client.post(
        "/api/tags/payment/initiate",
        headers={"Authorization": f"Bearer {create_access_token(subject='brand-1')}"},
        json={"product_type": "Sneakers", "vendor_id": "vendor-9"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Vendor 'vendor-9' not found."
