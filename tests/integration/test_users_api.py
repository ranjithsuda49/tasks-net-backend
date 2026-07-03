def test_create_and_fetch_user(client):
    create_response = client.post(
        "/api/v1/users",
        json={"firstName": "Ada", "lastName": "Lovelace", "emailId": "ada@example.com"},
    )
    assert create_response.status_code == 201
    body = create_response.json()
    assert body["name"] == {"firstName": "Ada", "lastName": "Lovelace"}
    assert body["userStatus"] == "ACTIVE"
    user_id = body["userId"]

    fetch_response = client.get(f"/api/v1/users/{user_id}")
    assert fetch_response.status_code == 200
    assert fetch_response.json()["userId"] == user_id


def test_fetch_unknown_user_returns_404(client):
    response = client.get("/api/v1/users/does-not-exist")
    assert response.status_code == 404


def test_update_user_fields(client):
    user_id = client.post(
        "/api/v1/users", json={"firstName": "Ada", "lastName": "Lovelace"}
    ).json()["userId"]

    response = client.patch(f"/api/v1/users/{user_id}", json={"lastName": "King"})
    assert response.status_code == 200
    assert response.json()["name"]["lastName"] == "King"


def test_update_user_status(client):
    user_id = client.post(
        "/api/v1/users", json={"firstName": "Ada", "lastName": "Lovelace"}
    ).json()["userId"]

    response = client.patch(
        f"/api/v1/users/{user_id}/status", json={"userStatus": "IN-ACTIVE"}
    )
    assert response.status_code == 200
    assert response.json()["userStatus"] == "IN-ACTIVE"
