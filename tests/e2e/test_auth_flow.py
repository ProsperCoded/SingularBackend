from __future__ import annotations


def test_signup_login_and_me_flow(client) -> None:
    signup_response = client.post(
        "/api/auth/signup",
        json={
                "full_name": "Brand Owner",
                "email": "brand@example.com",
                "password": "secretpass123",
                "role": "brand",
            },
        )

    assert signup_response.status_code == 201
    signup_body = signup_response.json()
    assert signup_body["user"]["full_name"] == "Brand Owner"
    assert signup_body["user"]["email"] == "brand@example.com"
    assert signup_body["user"]["role"] == "brand"
    assert signup_body["access_token"]

    login_response = client.post(
        "/api/auth/login",
        json={
            "email": "brand@example.com",
            "password": "secretpass123",
        },
    )

    assert login_response.status_code == 200
    login_body = login_response.json()
    assert login_body["user"]["email"] == "brand@example.com"
    assert login_body["access_token"]

    me_response = client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {login_body['access_token']}"},
    )

    assert me_response.status_code == 200
    me_body = me_response.json()
    assert me_body["email"] == "brand@example.com"
    assert me_body["full_name"] == "Brand Owner"


def test_signup_rejects_duplicate_email(client) -> None:
    payload = {
        "full_name": "Brand Owner",
        "email": "brand@example.com",
        "password": "secretpass123",
        "role": "brand",
    }

    first_response = client.post("/api/auth/signup", json=payload)
    second_response = client.post("/api/auth/signup", json=payload)

    assert first_response.status_code == 201
    assert second_response.status_code == 409
