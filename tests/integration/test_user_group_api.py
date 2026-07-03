def _create_user(client, first_name="Ada", last_name="Lovelace"):
    return client.post(
        "/api/v1/users", json={"firstName": first_name, "lastName": last_name}
    ).json()["userId"]


def _create_group(client, creator_id):
    return client.post(
        "/api/v1/groups",
        json={"groupName": "Smiths", "groupCategory": "Family", "groupCreaterId": creator_id},
    ).json()["groupId"]


def test_associate_user_to_group(client):
    creator_id = _create_user(client)
    group_id = _create_group(client, creator_id)

    response = client.post(
        f"/api/v1/groups/{group_id}/members", json={"userId": creator_id, "relationship": "Father"}
    )
    assert response.status_code == 201
    body = response.json()
    assert body["userId"] == creator_id
    assert body["groupId"] == group_id
    assert body["relationship"] == "Father"


def test_associate_duplicate_returns_400(client):
    creator_id = _create_user(client)
    group_id = _create_group(client, creator_id)
    client.post(
        f"/api/v1/groups/{group_id}/members", json={"userId": creator_id, "relationship": "Father"}
    )

    response = client.post(
        f"/api/v1/groups/{group_id}/members", json={"userId": creator_id, "relationship": "Father"}
    )
    assert response.status_code == 400
    assert response.json()["detail"]["errorCode"] == "ERR_TASKS_003"


def test_associate_unknown_user_returns_404(client):
    creator_id = _create_user(client)
    group_id = _create_group(client, creator_id)

    response = client.post(
        f"/api/v1/groups/{group_id}/members", json={"userId": "unknown", "relationship": "Father"}
    )
    assert response.status_code == 404


def test_disassociate_user_from_group(client):
    creator_id = _create_user(client)
    group_id = _create_group(client, creator_id)
    client.post(
        f"/api/v1/groups/{group_id}/members", json={"userId": creator_id, "relationship": "Father"}
    )

    response = client.delete(f"/api/v1/groups/{group_id}/members/{creator_id}")
    assert response.status_code == 204


def test_disassociate_unknown_association_returns_404(client):
    creator_id = _create_user(client)
    group_id = _create_group(client, creator_id)

    response = client.delete(f"/api/v1/groups/{group_id}/members/{creator_id}")
    assert response.status_code == 404
