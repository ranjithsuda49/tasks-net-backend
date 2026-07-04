def _create_user(client, first_name="Ada", last_name="Lovelace"):
    return client.post(
        "/api/v1/users", json={"firstName": first_name, "lastName": last_name}
    ).json()["userId"]


def _create_group(client, creator_id):
    return client.post(
        "/api/v1/groups",
        json={"groupName": "Smiths", "groupCategory": "Family", "groupCreaterId": creator_id},
    ).json()["groupId"]


def test_associate_user_to_group(client, authenticate_as):
    creator_id = _create_user(client)
    member_id = _create_user(client, first_name="Bob", last_name="Smith")
    group_id = _create_group(client, creator_id)

    authenticate_as(creator_id)
    response = client.post(
        f"/api/v1/groups/{group_id}/members", json={"userId": member_id, "relationship": "Father"}
    )
    assert response.status_code == 201
    body = response.json()
    assert body["userId"] == member_id
    assert body["groupId"] == group_id
    assert body["relationship"] == "Father"


def test_associate_non_member_non_creator_returns_403(client):
    creator_id = _create_user(client)
    member_id = _create_user(client, first_name="Bob", last_name="Smith")
    group_id = _create_group(client, creator_id)

    response = client.post(
        f"/api/v1/groups/{group_id}/members", json={"userId": member_id, "relationship": "Father"}
    )
    assert response.status_code == 403


def test_associate_duplicate_returns_400(client, authenticate_as):
    creator_id = _create_user(client)
    member_id = _create_user(client, first_name="Bob", last_name="Smith")
    group_id = _create_group(client, creator_id)
    authenticate_as(creator_id)
    client.post(
        f"/api/v1/groups/{group_id}/members", json={"userId": member_id, "relationship": "Father"}
    )

    response = client.post(
        f"/api/v1/groups/{group_id}/members", json={"userId": member_id, "relationship": "Father"}
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


def test_associate_group_creator_returns_400(client, authenticate_as):
    creator_id = _create_user(client)
    group_id = _create_group(client, creator_id)

    authenticate_as(creator_id)
    response = client.post(
        f"/api/v1/groups/{group_id}/members", json={"userId": creator_id, "relationship": "Father"}
    )
    assert response.status_code == 400
    assert response.json()["detail"]["errorCode"] == "ERR_TASKS_006"


def test_disassociate_user_from_group(client, authenticate_as):
    creator_id = _create_user(client)
    member_id = _create_user(client, first_name="Bob", last_name="Smith")
    group_id = _create_group(client, creator_id)
    authenticate_as(creator_id)
    client.post(
        f"/api/v1/groups/{group_id}/members", json={"userId": member_id, "relationship": "Father"}
    )

    response = client.delete(f"/api/v1/groups/{group_id}/members/{member_id}")
    assert response.status_code == 204


def test_disassociate_self_succeeds(client, authenticate_as):
    creator_id = _create_user(client)
    member_id = _create_user(client, first_name="Bob", last_name="Smith")
    group_id = _create_group(client, creator_id)
    authenticate_as(creator_id)
    client.post(
        f"/api/v1/groups/{group_id}/members", json={"userId": member_id, "relationship": "Father"}
    )

    authenticate_as(member_id)
    response = client.delete(f"/api/v1/groups/{group_id}/members/{member_id}")
    assert response.status_code == 204


def test_disassociate_wrong_user_returns_403(client, authenticate_as):
    creator_id = _create_user(client)
    member_id = _create_user(client, first_name="Bob", last_name="Smith")
    outsider_id = _create_user(client, first_name="Cara", last_name="Jones")
    group_id = _create_group(client, creator_id)
    authenticate_as(creator_id)
    client.post(
        f"/api/v1/groups/{group_id}/members", json={"userId": member_id, "relationship": "Father"}
    )

    authenticate_as(outsider_id)
    response = client.delete(f"/api/v1/groups/{group_id}/members/{member_id}")
    assert response.status_code == 403


def test_disassociate_unknown_association_returns_404(client, authenticate_as):
    creator_id = _create_user(client)
    group_id = _create_group(client, creator_id)

    authenticate_as(creator_id)
    response = client.delete(f"/api/v1/groups/{group_id}/members/{creator_id}")
    assert response.status_code == 404


def test_get_group_members_returns_associated_users(client, authenticate_as):
    creator_id = _create_user(client)
    member_id = _create_user(client, first_name="Bob", last_name="Smith")
    group_id = _create_group(client, creator_id)
    authenticate_as(creator_id)
    client.post(
        f"/api/v1/groups/{group_id}/members", json={"userId": member_id, "relationship": "Father"}
    )

    response = client.get(f"/api/v1/groups/{group_id}/members")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["userId"] == member_id
    assert body[0]["groupId"] == group_id
    assert body[0]["relationship"] == "Father"


def test_get_group_members_non_member_returns_403(client):
    creator_id = _create_user(client)
    group_id = _create_group(client, creator_id)

    response = client.get(f"/api/v1/groups/{group_id}/members")
    assert response.status_code == 403


def test_get_group_members_empty_list_for_group_with_no_members(client, authenticate_as):
    creator_id = _create_user(client)
    group_id = _create_group(client, creator_id)

    authenticate_as(creator_id)
    response = client.get(f"/api/v1/groups/{group_id}/members")
    assert response.status_code == 200
    assert response.json() == []


def test_get_group_members_unknown_group_returns_404(client):
    response = client.get("/api/v1/groups/unknown-group/members")
    assert response.status_code == 404
