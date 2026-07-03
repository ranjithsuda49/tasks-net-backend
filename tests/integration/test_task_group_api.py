def _create_user(client, first_name="Ada", last_name="Lovelace"):
    return client.post(
        "/api/v1/users", json={"firstName": first_name, "lastName": last_name}
    ).json()["userId"]


def _create_group(client, creator_id):
    return client.post(
        "/api/v1/groups",
        json={"groupName": "Smiths", "groupCategory": "Family", "groupCreaterId": creator_id},
    ).json()["groupId"]


def _create_task(client, creator_id):
    return client.post(
        "/api/v1/tasks", json={"taskTitle": "Buy milk", "createdBy": creator_id}
    ).json()["taskId"]


def test_assign_task_to_group_member(client):
    creator_id = _create_user(client)
    group_id = _create_group(client, creator_id)
    task_id = _create_task(client, creator_id)

    response = client.post(
        f"/api/v1/groups/{group_id}/tasks/{task_id}/assignee", json={"assigneeId": creator_id}
    )
    assert response.status_code == 201
    body = response.json()
    assert body["taskId"] == task_id
    assert body["groupId"] == group_id
    assert body["assigneeId"] == creator_id


def test_assign_task_unknown_assignee_returns_404(client):
    creator_id = _create_user(client)
    group_id = _create_group(client, creator_id)
    task_id = _create_task(client, creator_id)

    response = client.post(
        f"/api/v1/groups/{group_id}/tasks/{task_id}/assignee", json={"assigneeId": "unknown"}
    )
    assert response.status_code == 404


def test_unassign_task(client):
    creator_id = _create_user(client)
    group_id = _create_group(client, creator_id)
    task_id = _create_task(client, creator_id)
    client.post(f"/api/v1/groups/{group_id}/tasks/{task_id}/assignee", json={"assigneeId": creator_id})

    response = client.delete(f"/api/v1/groups/{group_id}/tasks/{task_id}/assignee/{creator_id}")
    assert response.status_code == 200
    assert response.json()["assigneeId"] is None


def test_unassign_task_without_prior_assignment_returns_404(client):
    creator_id = _create_user(client)
    group_id = _create_group(client, creator_id)
    task_id = _create_task(client, creator_id)

    response = client.delete(f"/api/v1/groups/{group_id}/tasks/{task_id}/assignee/{creator_id}")
    assert response.status_code == 404
