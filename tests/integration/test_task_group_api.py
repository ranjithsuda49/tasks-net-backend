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


def _seed_assignment(db_session, task_id, group_id, assignee_id):
    import uuid

    from app.models.task_group import TaskGroupRelationship
    from app.repositories.task_group_repository import TaskGroupRepository

    TaskGroupRepository(db_session).add(
        TaskGroupRelationship(uuid=str(uuid.uuid4()), taskId=task_id, groupId=group_id, assigneeId=assignee_id)
    )


def test_assign_route_removed_returns_405(client, authenticate_as):
    creator_id = _create_user(client, authenticate_as, "creator")
    group_id = _create_group(client, authenticate_as, creator_id)
    task_id = _create_task(client, authenticate_as, creator_id)
    response = client.post(
        f"/api/v1/groups/{group_id}/tasks/{task_id}/assignee", json={"assigneeId": creator_id}
    )
    # PATCH (reassign) still lives at this exact path, so removing POST
    # leaves the path resolvable but the method unsupported (405), unlike
    # the earlier DELETE-removal case at a sub-path with no other method.
    assert response.status_code == 405


def test_delete_assignee_route_removed_returns_404(client, authenticate_as):
    creator_id = _create_user(client, authenticate_as, "creator")
    group_id = _create_group(client, authenticate_as, creator_id)
    task_id = _create_task(client, authenticate_as, creator_id)
    response = client.delete(f"/api/v1/groups/{group_id}/tasks/{task_id}/assignee/{creator_id}")
    assert response.status_code == 404


def test_reassign_task_to_new_member_succeeds(client, authenticate_as, db_session):
    creator_id = _create_user(client, authenticate_as, "creator")
    member_id = _create_user(client, authenticate_as, "member", first_name="Bob", last_name="Smith")
    other_member_id = _create_user(client, authenticate_as, "other", first_name="Cara", last_name="Jones")
    group_id = _create_group(client, authenticate_as, creator_id)
    task_id = _create_task(client, authenticate_as, creator_id)
    _associate_user(client, group_id, member_id)
    _associate_user(client, group_id, other_member_id)
    _seed_assignment(db_session, task_id, group_id, member_id)

    response = client.patch(
        f"/api/v1/groups/{group_id}/tasks/{task_id}/assignee", json={"assigneeId": other_member_id}
    )
    assert response.status_code == 200
    assert response.json()["assigneeId"] == other_member_id


def test_reassign_task_same_assignee_returns_400_err_007(client, authenticate_as, db_session):
    creator_id = _create_user(client, authenticate_as, "creator")
    member_id = _create_user(client, authenticate_as, "member", first_name="Bob", last_name="Smith")
    group_id = _create_group(client, authenticate_as, creator_id)
    task_id = _create_task(client, authenticate_as, creator_id)
    _associate_user(client, group_id, member_id)
    _seed_assignment(db_session, task_id, group_id, member_id)

    response = client.patch(
        f"/api/v1/groups/{group_id}/tasks/{task_id}/assignee", json={"assigneeId": member_id}
    )
    assert response.status_code == 400
    assert response.json()["detail"]["errorCode"] == "ERR_TASKS_007"


def test_reassign_task_non_member_returns_400_err_008(client, authenticate_as, db_session):
    creator_id = _create_user(client, authenticate_as, "creator")
    member_id = _create_user(client, authenticate_as, "member", first_name="Bob", last_name="Smith")
    outsider_id = _create_user(client, authenticate_as, "outsider", first_name="Cara", last_name="Jones")
    group_id = _create_group(client, authenticate_as, creator_id)
    task_id = _create_task(client, authenticate_as, creator_id)
    _associate_user(client, group_id, member_id)
    _seed_assignment(db_session, task_id, group_id, member_id)

    response = client.patch(
        f"/api/v1/groups/{group_id}/tasks/{task_id}/assignee", json={"assigneeId": outsider_id}
    )
    assert response.status_code == 400
    assert response.json()["detail"]["errorCode"] == "ERR_TASKS_008"


def test_reassign_task_any_member_can_call_not_just_creator(client, authenticate_as, db_session):
    creator_id = _create_user(client, authenticate_as, "creator")
    member_id = _create_user(client, authenticate_as, "member", first_name="Bob", last_name="Smith")
    group_id = _create_group(client, authenticate_as, creator_id)
    task_id = _create_task(client, authenticate_as, creator_id)
    _associate_user(client, group_id, member_id)
    _seed_assignment(db_session, task_id, group_id, member_id)

    authenticate_as(member_id)
    response = client.patch(
        f"/api/v1/groups/{group_id}/tasks/{task_id}/assignee", json={"assigneeId": creator_id}
    )
    assert response.status_code == 200
    assert response.json()["assigneeId"] == creator_id


def test_reassign_task_non_member_caller_returns_403(client, authenticate_as, db_session):
    creator_id = _create_user(client, authenticate_as, "creator")
    member_id = _create_user(client, authenticate_as, "member", first_name="Bob", last_name="Smith")
    group_id = _create_group(client, authenticate_as, creator_id)
    task_id = _create_task(client, authenticate_as, creator_id)
    _associate_user(client, group_id, member_id)
    _seed_assignment(db_session, task_id, group_id, member_id)

    authenticate_as("outsider")
    response = client.patch(
        f"/api/v1/groups/{group_id}/tasks/{task_id}/assignee", json={"assigneeId": creator_id}
    )
    assert response.status_code == 403


def test_list_group_tasks_as_creator(client, authenticate_as):
    creator_id = _create_user(client, authenticate_as, "creator")
    group_id = _create_group(client, authenticate_as, creator_id)
    task_id = client.post(
        "/api/v1/tasks", json={"taskTitle": "Buy milk", "groupId": group_id}
    ).json()["taskId"]

    response = client.get(f"/api/v1/groups/{group_id}/tasks")
    assert response.status_code == 200
    assert [t["taskId"] for t in response.json()] == [task_id]


def test_list_group_tasks_as_member(client, authenticate_as):
    creator_id = _create_user(client, authenticate_as, "creator")
    member_id = _create_user(client, authenticate_as, "member", first_name="Bob", last_name="Smith")
    group_id = _create_group(client, authenticate_as, creator_id)
    _associate_user(client, group_id, member_id)
    client.post("/api/v1/tasks", json={"taskTitle": "Buy milk", "groupId": group_id})

    authenticate_as(member_id)
    response = client.get(f"/api/v1/groups/{group_id}/tasks")
    assert response.status_code == 200
    assert len(response.json()) == 1


def test_list_group_tasks_non_member_returns_403(client, authenticate_as):
    creator_id = _create_user(client, authenticate_as, "creator")
    group_id = _create_group(client, authenticate_as, creator_id)

    authenticate_as("outsider")
    response = client.get(f"/api/v1/groups/{group_id}/tasks")
    assert response.status_code == 403


def test_list_group_tasks_unknown_group_returns_404(client, authenticate_as):
    _create_user(client, authenticate_as, "creator")
    response = client.get("/api/v1/groups/unknown-group/tasks")
    assert response.status_code == 404
