from __future__ import annotations

from fastapi.testclient import TestClient
import pytest

from core.database import get_db_session
from core.security import create_access_token, hash_password, verify_password
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
        self.added: list[object] = []
        self.commits = 0
        self.refreshed: list[object] = []

    async def exec(self, _statement):
        rows = self.exec_results.pop(0) if self.exec_results else []
        return FakeResult(rows or [])

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


def _client_for(session: FakeSession) -> TestClient:
    async def _override_session():
        yield session

    app.dependency_overrides[get_db_session] = _override_session
    return TestClient(app)


def test_signup_creates_user_and_returns_token() -> None:
    session = FakeSession(exec_results=[[]])
    client = _client_for(session)

    response = client.post(
        "/api/auth/signup",
        json={
            "full_name": "Brand Owner",
            "email": "brand@example.test",
            "password": "secretpass",
            "role": "brand",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["user"]["email"] == "brand@example.test"
    assert body["user"]["role"] == "brand"
    assert session.commits == 1
    created_user = session.added[0]
    assert created_user.full_name == "Brand Owner"
    assert verify_password("secretpass", created_user.password_hash)


def test_signup_rejects_duplicate_email() -> None:
    existing_user = User(email="brand@example.test", role=UserRole.BRAND)
    session = FakeSession(exec_results=[[existing_user]])
    client = _client_for(session)

    response = client.post(
        "/api/auth/signup",
        json={
            "full_name": "Brand Owner",
            "email": "brand@example.test",
            "password": "secretpass",
            "role": "brand",
        },
    )

    assert response.status_code == 409


def test_login_returns_token_for_valid_credentials() -> None:
    existing_user = User(
        id="user-1",
        full_name="Vendor One",
        email="vendor@example.test",
        role=UserRole.VENDOR,
    )
    existing_user.password_hash = hash_password("secretpass")
    session = FakeSession(exec_results=[[existing_user]])
    client = _client_for(session)

    response = client.post(
        "/api/auth/login",
        json={"email": "vendor@example.test", "password": "secretpass"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["user"]["role"] == "vendor"
    assert body["access_token"]


def test_login_rejects_invalid_password() -> None:
    existing_user = User(
        id="user-1",
        full_name="Vendor One",
        email="vendor@example.test",
        role=UserRole.VENDOR,
    )
    existing_user.password_hash = hash_password("secretpass")
    session = FakeSession(exec_results=[[existing_user]])
    client = _client_for(session)

    response = client.post(
        "/api/auth/login",
        json={"email": "vendor@example.test", "password": "wrongpass"},
    )

    assert response.status_code == 401


def test_me_returns_current_user_from_token() -> None:
    user = User(
        id="user-1",
        full_name="Brand Owner",
        email="brand@example.test",
        role=UserRole.BRAND,
    )
    session = FakeSession(exec_results=[[user]])
    client = _client_for(session)

    response = client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {create_access_token(subject='user-1')}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == "user-1"
    assert body["email"] == "brand@example.test"
