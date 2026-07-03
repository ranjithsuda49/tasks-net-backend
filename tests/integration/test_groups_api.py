def _create_user(client, first_name="Ada", last_name="Lovelace"):
    response = client.post("/api/v1/users", json={"firstName": first_name, "lastName": last_name})
    return response.json()["userId"]


def test_create_group_for_unknown_creator_returns_404(client):
    response = client.post(
        "/api/v1/groups",
        json={"groupName": "Smiths", "groupCategory": "Family", "groupCreaterId": "unknown"},
    )
    assert response.status_code == 404


def test_create_and_fetch_group(client):
    creator_id = _create_user(client)
    create_response = client.post(
        "/api/v1/groups",
        json={
            "groupName": "Smiths",
            "groupDesc": "Family group",
            "groupCategory": "Family",
            "groupCreaterId": creator_id,
        },
    )
    assert create_response.status_code == 201
    group_id = create_response.json()["groupId"]

    fetch_response = client.get(f"/api/v1/groups/{group_id}")
    assert fetch_response.status_code == 200
    assert fetch_response.json()["groupCreaterId"] == creator_id


def test_get_groups_by_creator(client):
    creator_id = _create_user(client)
    client.post(
        "/api/v1/groups",
        json={"groupName": "Smiths", "groupCategory": "Family", "groupCreaterId": creator_id},
    )

    response = client.get(f"/api/v1/users/{creator_id}/groups")
    assert response.status_code == 200
    groups = response.json()
    assert len(groups) == 1
    assert groups[0]["groupName"] == "Smiths"


def test_update_group_ignores_category_field(client):
    creator_id = _create_user(client)
    group_id = client.post(
        "/api/v1/groups",
        json={"groupName": "Smiths", "groupCategory": "Family", "groupCreaterId": creator_id},
    ).json()["groupId"]

    response = client.patch(f"/api/v1/groups/{group_id}", json={"groupName": "The Smiths"})
    assert response.status_code == 200
    body = response.json()
    assert body["groupName"] == "The Smiths"
    assert body["groupCategory"] == "Family"


def test_update_group_status(client):
    creator_id = _create_user(client)
    group_id = client.post(
        "/api/v1/groups",
        json={"groupName": "Smiths", "groupCategory": "Family", "groupCreaterId": creator_id},
    ).json()["groupId"]

    response = client.patch(f"/api/v1/groups/{group_id}/status", json={"groupStatus": "IN-ACTIVE"})
    assert response.status_code == 200
    assert response.json()["groupStatus"] == "IN-ACTIVE"
