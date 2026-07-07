from conftest import login


def test_valid_login_sets_current_user(client):
    login(client, "user1", "12345")

    response = client.get("/api/auth/me")

    assert response.status_code == 200
    assert response.json() == {"user_id": "user1"}


def test_invalid_login_is_rejected(client):
    response = client.post(
        "/api/auth/login",
        json={"username": "user1", "password": "wrong"},
    )

    assert response.status_code == 401


def test_protected_endpoint_without_cookie_is_rejected(client):
    response = client.get("/api/auth/me")

    assert response.status_code == 401
    assert response.json()["detail"] == "not_authenticated"
