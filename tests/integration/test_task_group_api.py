def _create_user(client, authenticate_as, user_id, first_name="Ada", last_name="Lovelace"):
    authenticate_as(user_id)
    return client.post(
        "/api/v1/users", json={"firstName": first_name, "lastName": last_name}
    ).json()["userId"]


def _create_group(client, authenticate_as, creator_id):
    authenticate_as(creator_id)
    return client.post(
        "/api/v1/groups", json={"groupName": "Smiths", "groupCategory": "Family"}
    ).json()["groupId"]


def _create_task(client, authenticate_as, creator_id):
    authenticate_as(creator_id)
    return client.post("/api/v1/tasks", json={"taskTitle": "Buy milk"}).json()["taskId"]


def _associate_user(client, group_id, user_id, relationship="Member"):
    return client.post(
        f"/api/v1/groups/{group_id}/members", json={"userId": user_id, "relationship": relationship}
    )


def test_assign_task_to_group_member(client, authenticate_as):
    creator_id = _create_user(client, authenticate_as, "creator")
    member_id = _create_user(client, authenticate_as, "member", first_name="Bob", last_name="Smith")
    group_id = _create_group(client, authenticate_as, creator_id)
    task_id = _create_task(client, authenticate_as, creator_id)
    _associate_user(client, group_id, member_id)

    response = client.post(
        f"/api/v1/groups/{group_id}/tasks/{task_id}/assignee", json={"assigneeId": member_id}
    )
    assert response.status_code == 201
    body = response.json()
    assert body["taskId"] == task_id
    assert body["groupId"] == group_id
    assert body["assigneeId"] == member_id


def test_assign_task_wrong_caller_returns_403(client, authenticate_as):
    creator_id = _create_user(client, authenticate_as, "creator")
    member_id = _create_user(client, authenticate_as, "member", first_name="Bob", last_name="Smith")
    group_id = _create_group(client, authenticate_as, creator_id)
    task_id = _create_task(client, authenticate_as, creator_id)
    _associate_user(client, group_id, member_id)

    authenticate_as(member_id)
    response = client.post(
        f"/api/v1/groups/{group_id}/tasks/{task_id}/assignee", json={"assigneeId": member_id}
    )
    assert response.status_code == 403


def test_assign_task_unknown_assignee_returns_404(client, authenticate_as):
    creator_id = _create_user(client, authenticate_as, "creator")
    group_id = _create_group(client, authenticate_as, creator_id)
    task_id = _create_task(client, authenticate_as, creator_id)

    response = client.post(
        f"/api/v1/groups/{group_id}/tasks/{task_id}/assignee", json={"assigneeId": "unknown"}
    )
    assert response.status_code == 404


def test_assign_task_to_non_member_returns_400(client, authenticate_as):
    creator_id = _create_user(client, authenticate_as, "creator")
    outsider_id = _create_user(client, authenticate_as, "outsider", first_name="Cara", last_name="Jones")
    group_id = _create_group(client, authenticate_as, creator_id)
    task_id = _create_task(client, authenticate_as, creator_id)

    response = client.post(
        f"/api/v1/groups/{group_id}/tasks/{task_id}/assignee", json={"assigneeId": outsider_id}
    )
    assert response.status_code == 400
    body = response.json()
    assert body["detail"]["errorCode"] == "ERR_TASKS_001"


def test_unassign_task(client, authenticate_as):
    creator_id = _create_user(client, authenticate_as, "creator")
    member_id = _create_user(client, authenticate_as, "member", first_name="Bob", last_name="Smith")
    group_id = _create_group(client, authenticate_as, creator_id)
    task_id = _create_task(client, authenticate_as, creator_id)
    _associate_user(client, group_id, member_id)
    client.post(f"/api/v1/groups/{group_id}/tasks/{task_id}/assignee", json={"assigneeId": member_id})

    response = client.delete(f"/api/v1/groups/{group_id}/tasks/{task_id}/assignee/{member_id}")
    assert response.status_code == 200
    assert response.json()["assigneeId"] is None


def test_unassign_task_wrong_caller_returns_403(client, authenticate_as):
    creator_id = _create_user(client, authenticate_as, "creator")
    member_id = _create_user(client, authenticate_as, "member", first_name="Bob", last_name="Smith")
    group_id = _create_group(client, authenticate_as, creator_id)
    task_id = _create_task(client, authenticate_as, creator_id)
    _associate_user(client, group_id, member_id)
    client.post(f"/api/v1/groups/{group_id}/tasks/{task_id}/assignee", json={"assigneeId": member_id})

    authenticate_as(member_id)
    response = client.delete(f"/api/v1/groups/{group_id}/tasks/{task_id}/assignee/{member_id}")
    assert response.status_code == 403


def test_unassign_task_without_prior_assignment_returns_404(client, authenticate_as):
    creator_id = _create_user(client, authenticate_as, "creator")
    group_id = _create_group(client, authenticate_as, creator_id)
    task_id = _create_task(client, authenticate_as, creator_id)

    response = client.delete(f"/api/v1/groups/{group_id}/tasks/{task_id}/assignee/{creator_id}")
    assert response.status_code == 404


def test_unassign_task_with_mismatched_assignee_returns_404(client, authenticate_as):
    creator_id = _create_user(client, authenticate_as, "creator")
    member_id = _create_user(client, authenticate_as, "member", first_name="Bob", last_name="Smith")
    other_user_id = _create_user(client, authenticate_as, "other", first_name="Cara", last_name="Jones")
    group_id = _create_group(client, authenticate_as, creator_id)
    task_id = _create_task(client, authenticate_as, creator_id)
    _associate_user(client, group_id, member_id)
    client.post(f"/api/v1/groups/{group_id}/tasks/{task_id}/assignee", json={"assigneeId": member_id})

    response = client.delete(f"/api/v1/groups/{group_id}/tasks/{task_id}/assignee/{other_user_id}")
    assert response.status_code == 404


def test_assign_task_to_creator_returns_400(client, authenticate_as):
    creator_id = _create_user(client, authenticate_as, "creator")
    group_id = _create_group(client, authenticate_as, creator_id)
    task_id = _create_task(client, authenticate_as, creator_id)

    response = client.post(
        f"/api/v1/groups/{group_id}/tasks/{task_id}/assignee", json={"assigneeId": creator_id}
    )
    assert response.status_code == 400
    assert response.json()["detail"]["errorCode"] == "ERR_TASKS_005"
