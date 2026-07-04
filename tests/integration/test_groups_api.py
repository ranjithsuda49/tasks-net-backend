def _create_user(client, authenticate_as, user_id, first_name="Ada", last_name="Lovelace"):
    authenticate_as(user_id)
    response = client.post("/api/v1/users", json={"firstName": first_name, "lastName": last_name})
    return response.json()["userId"]


def test_create_group_for_unknown_creator_returns_404(client):
    response = client.post(
        "/api/v1/groups",
        json={"groupName": "Smiths", "groupCategory": "Family"},
    )
    assert response.status_code == 404


def test_create_and_fetch_group(client, authenticate_as):
    creator_id = _create_user(client, authenticate_as, "creator")
    create_response = client.post(
        "/api/v1/groups",
        json={
            "groupName": "Smiths",
            "groupDesc": "Family group",
            "groupCategory": "Family",
        },
    )
    assert create_response.status_code == 201
    group_id = create_response.json()["groupId"]

    fetch_response = client.get(f"/api/v1/groups/{group_id}")
    assert fetch_response.status_code == 200
    assert fetch_response.json()["groupCreaterId"] == creator_id


def test_get_group_non_member_non_creator_returns_403(client, authenticate_as):
    _create_user(client, authenticate_as, "creator")
    group_id = client.post(
        "/api/v1/groups",
        json={"groupName": "Smiths", "groupCategory": "Family"},
    ).json()["groupId"]

    authenticate_as("outsider")
    response = client.get(f"/api/v1/groups/{group_id}")
    assert response.status_code == 403


def test_get_groups_by_creator(client, authenticate_as):
    creator_id = _create_user(client, authenticate_as, "creator")
    client.post(
        "/api/v1/groups",
        json={"groupName": "Smiths", "groupCategory": "Family"},
    )

    response = client.get(f"/api/v1/users/{creator_id}/groups")
    assert response.status_code == 200
    groups = response.json()
    assert len(groups) == 1
    assert groups[0]["groupName"] == "Smiths"


def test_get_groups_by_creator_wrong_caller_returns_403(client, authenticate_as):
    creator_id = _create_user(client, authenticate_as, "creator")

    authenticate_as("outsider")
    response = client.get(f"/api/v1/users/{creator_id}/groups")
    assert response.status_code == 403


def test_update_group_ignores_category_field(client, authenticate_as):
    _create_user(client, authenticate_as, "creator")
    group_id = client.post(
        "/api/v1/groups",
        json={"groupName": "Smiths", "groupCategory": "Family"},
    ).json()["groupId"]

    response = client.patch(f"/api/v1/groups/{group_id}", json={"groupName": "The Smiths"})
    assert response.status_code == 200
    body = response.json()
    assert body["groupName"] == "The Smiths"
    assert body["groupCategory"] == "Family"


def test_update_group_non_creator_returns_403(client, authenticate_as):
    _create_user(client, authenticate_as, "creator")
    group_id = client.post(
        "/api/v1/groups",
        json={"groupName": "Smiths", "groupCategory": "Family"},
    ).json()["groupId"]

    authenticate_as("outsider")
    response = client.patch(f"/api/v1/groups/{group_id}", json={"groupName": "The Smiths"})
    assert response.status_code == 403


def test_update_group_status(client, authenticate_as):
    _create_user(client, authenticate_as, "creator")
    group_id = client.post(
        "/api/v1/groups",
        json={"groupName": "Smiths", "groupCategory": "Family"},
    ).json()["groupId"]

    response = client.patch(f"/api/v1/groups/{group_id}/status", json={"groupStatus": "IN-ACTIVE"})
    assert response.status_code == 200
    assert response.json()["groupStatus"] == "IN-ACTIVE"
