def _create_user(client, authenticate_as, user_id, first_name="Ada", last_name="Lovelace"):
    authenticate_as(user_id)
    return client.post(
        "/api/v1/users", json={"firstName": first_name, "lastName": last_name}
    ).json()["userId"]


def test_create_and_fetch_task(client, authenticate_as):
    _create_user(client, authenticate_as, "user")
    create_response = client.post("/api/v1/tasks", json={"taskTitle": "Buy milk"})
    assert create_response.status_code == 201
    body = create_response.json()
    assert body["taskState"] == "TODO"
    task_id = body["taskId"]

    fetch_response = client.get(f"/api/v1/tasks/{task_id}")
    assert fetch_response.status_code == 200
    assert fetch_response.json()["taskId"] == task_id


def test_create_task_unknown_user_returns_404(client):
    response = client.post("/api/v1/tasks", json={"taskTitle": "Buy milk"})
    assert response.status_code == 404


def test_get_task_wrong_caller_returns_403(client, authenticate_as):
    _create_user(client, authenticate_as, "user")
    task_id = client.post("/api/v1/tasks", json={"taskTitle": "Buy milk"}).json()["taskId"]

    authenticate_as("outsider")
    response = client.get(f"/api/v1/tasks/{task_id}")
    assert response.status_code == 403


def test_update_task_meta(client, authenticate_as):
    user_id = _create_user(client, authenticate_as, "user")
    task_id = client.post("/api/v1/tasks", json={"taskTitle": "Buy milk"}).json()["taskId"]

    response = client.patch(
        f"/api/v1/tasks/{task_id}", json={"taskTitle": "Buy oat milk"}
    )
    assert response.status_code == 200
    assert response.json()["taskTitle"] == "Buy oat milk"


def test_update_task_meta_non_creator_returns_403(client, authenticate_as):
    user_id = _create_user(client, authenticate_as, "user")
    task_id = client.post("/api/v1/tasks", json={"taskTitle": "Buy milk"}).json()["taskId"]

    authenticate_as("outsider")
    response = client.patch(
        f"/api/v1/tasks/{task_id}", json={"taskTitle": "Buy oat milk"}
    )
    assert response.status_code == 403


def test_update_task_state(client, authenticate_as):
    user_id = _create_user(client, authenticate_as, "user")
    task_id = client.post("/api/v1/tasks", json={"taskTitle": "Buy milk"}).json()["taskId"]

    response = client.patch(
        f"/api/v1/tasks/{task_id}/state", json={"taskState": "IN-PROGRESS"}
    )
    assert response.status_code == 200
    assert response.json()["taskState"] == "IN-PROGRESS"


def test_update_task_state_already_completed_returns_400(client, authenticate_as):
    user_id = _create_user(client, authenticate_as, "user")
    task_id = client.post("/api/v1/tasks", json={"taskTitle": "Buy milk"}).json()["taskId"]
    client.patch(f"/api/v1/tasks/{task_id}/state", json={"taskState": "COMPLETED"})

    response = client.patch(
        f"/api/v1/tasks/{task_id}/state", json={"taskState": "COMPLETED"}
    )
    assert response.status_code == 400
    assert response.json()["detail"]["errorCode"] == "ERR_TASKS_002"


def test_update_task_state_allows_moving_out_of_completed(client, authenticate_as):
    user_id = _create_user(client, authenticate_as, "user")
    task_id = client.post("/api/v1/tasks", json={"taskTitle": "Buy milk"}).json()["taskId"]
    client.patch(f"/api/v1/tasks/{task_id}/state", json={"taskState": "COMPLETED"})

    response = client.patch(
        f"/api/v1/tasks/{task_id}/state", json={"taskState": "TODO"}
    )
    assert response.status_code == 200
    assert response.json()["taskState"] == "TODO"


def test_update_task_due_date(client, authenticate_as):
    user_id = _create_user(client, authenticate_as, "user")
    task_id = client.post("/api/v1/tasks", json={"taskTitle": "Buy milk"}).json()["taskId"]

    response = client.patch(
        f"/api/v1/tasks/{task_id}/due-date",
        json={"taskDueDate": "2026-08-01T00:00:00Z"},
    )
    assert response.status_code == 200
    assert response.json()["taskDueDate"].startswith("2026-08-01")


def test_update_task_due_date_to_null_clears_it(client, authenticate_as):
    user_id = _create_user(client, authenticate_as, "user")
    task_id = client.post("/api/v1/tasks", json={"taskTitle": "Buy milk"}).json()["taskId"]
    client.patch(
        f"/api/v1/tasks/{task_id}/due-date",
        json={"taskDueDate": "2026-08-01T00:00:00Z"},
    )

    response = client.patch(
        f"/api/v1/tasks/{task_id}/due-date",
        json={"taskDueDate": None},
    )
    assert response.status_code == 200
    assert response.json()["taskDueDate"] is None


def test_update_task_state_same_state_returns_400(client, authenticate_as):
    user_id = _create_user(client, authenticate_as, "user")
    task_id = client.post("/api/v1/tasks", json={"taskTitle": "Buy milk"}).json()["taskId"]

    response = client.patch(
        f"/api/v1/tasks/{task_id}/state", json={"taskState": "TODO"}
    )
    assert response.status_code == 400
    assert response.json()["detail"]["errorCode"] == "ERR_TASKS_002"


def test_list_my_tasks_returns_created_and_assigned(client, authenticate_as):
    owner_id = _create_user(client, authenticate_as, "owner")
    my_task_id = client.post("/api/v1/tasks", json={"taskTitle": "My task"}).json()["taskId"]

    _create_user(client, authenticate_as, "other", first_name="Bob", last_name="Smith")
    client.post("/api/v1/tasks", json={"taskTitle": "Not mine"})

    authenticate_as(owner_id)
    response = client.get("/api/v1/tasks")
    assert response.status_code == 200
    task_ids = [t["taskId"] for t in response.json()]
    assert my_task_id in task_ids


def test_create_task_with_group_id_returns_group_id_in_response(client, authenticate_as):
    creator_id = _create_user(client, authenticate_as, "creator")
    group_id = client.post(
        "/api/v1/groups", json={"groupName": "Smiths", "groupCategory": "Family"}
    ).json()["groupId"]

    response = client.post("/api/v1/tasks", json={"taskTitle": "Buy milk", "groupId": group_id})
    assert response.status_code == 201
    assert response.json()["groupId"] == group_id


def test_create_task_with_unknown_group_id_returns_404(client, authenticate_as):
    _create_user(client, authenticate_as, "creator")
    response = client.post(
        "/api/v1/tasks", json={"taskTitle": "Buy milk", "groupId": "unknown-group"}
    )
    assert response.status_code == 404


def test_create_task_with_group_id_non_member_returns_403(client, authenticate_as):
    creator_id = _create_user(client, authenticate_as, "creator")
    group_id = client.post(
        "/api/v1/groups", json={"groupName": "Smiths", "groupCategory": "Family"}
    ).json()["groupId"]
    _create_user(client, authenticate_as, "outsider", first_name="Cara", last_name="Jones")

    response = client.post("/api/v1/tasks", json={"taskTitle": "Buy milk", "groupId": group_id})
    assert response.status_code == 403


def test_get_task_returns_group_id_field(client, authenticate_as):
    creator_id = _create_user(client, authenticate_as, "creator")
    group_id = client.post(
        "/api/v1/groups", json={"groupName": "Smiths", "groupCategory": "Family"}
    ).json()["groupId"]
    task_id = client.post(
        "/api/v1/tasks", json={"taskTitle": "Buy milk", "groupId": group_id}
    ).json()["taskId"]

    response = client.get(f"/api/v1/tasks/{task_id}")
    assert response.json()["groupId"] == group_id


def test_update_task_meta_cannot_change_group_id(client, authenticate_as):
    creator_id = _create_user(client, authenticate_as, "creator")
    group_id = client.post(
        "/api/v1/groups", json={"groupName": "Smiths", "groupCategory": "Family"}
    ).json()["groupId"]
    task_id = client.post(
        "/api/v1/tasks", json={"taskTitle": "Buy milk", "groupId": group_id}
    ).json()["taskId"]

    response = client.patch(
        f"/api/v1/tasks/{task_id}", json={"taskTitle": "Buy oat milk", "groupId": "other-group"}
    )
    assert response.status_code == 200
    assert response.json()["groupId"] == group_id
