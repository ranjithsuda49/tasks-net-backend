def test_protected_route_without_authorization_header_returns_401(unauthenticated_client):
    response = unauthenticated_client.get("/api/v1/users/some-id")
    assert response.status_code == 401


def test_protected_route_with_malformed_header_returns_401(unauthenticated_client):
    response = unauthenticated_client.get(
        "/api/v1/users/some-id", headers={"Authorization": "Token abc123"}
    )
    assert response.status_code == 401


def test_create_user_without_authorization_header_returns_401(unauthenticated_client):
    response = unauthenticated_client.post(
        "/api/v1/users",
        json={"firstName": "Ada", "lastName": "Lovelace"},
    )
    assert response.status_code == 401
