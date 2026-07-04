def _create_user(client, first_name="Ada", last_name="Lovelace"):
    return client.post(
        "/api/v1/users", json={"firstName": first_name, "lastName": last_name}
    ).json()["userId"]


def test_create_and_fetch_task(client, authenticate_as):
    user_id = _create_user(client)
    create_response = client.post(
        "/api/v1/tasks", json={"taskTitle": "Buy milk", "createdBy": user_id}
    )
    assert create_response.status_code == 201
    body = create_response.json()
    assert body["taskState"] == "TODO"
    task_id = body["taskId"]

    authenticate_as(user_id)
    fetch_response = client.get(f"/api/v1/tasks/{task_id}")
    assert fetch_response.status_code == 200
    assert fetch_response.json()["taskId"] == task_id


def test_create_task_unknown_user_returns_404(client):
    response = client.post("/api/v1/tasks", json={"taskTitle": "Buy milk", "createdBy": "unknown"})
    assert response.status_code == 404


def test_get_task_wrong_caller_returns_403(client):
    user_id = _create_user(client)
    task_id = client.post(
        "/api/v1/tasks", json={"taskTitle": "Buy milk", "createdBy": user_id}
    ).json()["taskId"]

    response = client.get(f"/api/v1/tasks/{task_id}")
    assert response.status_code == 403


def test_update_task_meta(client, authenticate_as):
    user_id = _create_user(client)
    task_id = client.post(
        "/api/v1/tasks", json={"taskTitle": "Buy milk", "createdBy": user_id}
    ).json()["taskId"]

    authenticate_as(user_id)
    response = client.patch(
        f"/api/v1/tasks/{task_id}", json={"updatedBy": user_id, "taskTitle": "Buy oat milk"}
    )
    assert response.status_code == 200
    assert response.json()["taskTitle"] == "Buy oat milk"


def test_update_task_meta_non_creator_returns_403(client):
    user_id = _create_user(client)
    task_id = client.post(
        "/api/v1/tasks", json={"taskTitle": "Buy milk", "createdBy": user_id}
    ).json()["taskId"]

    response = client.patch(
        f"/api/v1/tasks/{task_id}", json={"updatedBy": user_id, "taskTitle": "Buy oat milk"}
    )
    assert response.status_code == 403


def test_update_task_state(client, authenticate_as):
    user_id = _create_user(client)
    task_id = client.post(
        "/api/v1/tasks", json={"taskTitle": "Buy milk", "createdBy": user_id}
    ).json()["taskId"]

    authenticate_as(user_id)
    response = client.patch(
        f"/api/v1/tasks/{task_id}/state", json={"updatedBy": user_id, "taskState": "IN-PROGRESS"}
    )
    assert response.status_code == 200
    assert response.json()["taskState"] == "IN-PROGRESS"


def test_update_task_state_already_completed_returns_400(client, authenticate_as):
    user_id = _create_user(client)
    task_id = client.post(
        "/api/v1/tasks", json={"taskTitle": "Buy milk", "createdBy": user_id}
    ).json()["taskId"]
    authenticate_as(user_id)
    client.patch(f"/api/v1/tasks/{task_id}/state", json={"updatedBy": user_id, "taskState": "COMPLETED"})

    response = client.patch(
        f"/api/v1/tasks/{task_id}/state", json={"updatedBy": user_id, "taskState": "COMPLETED"}
    )
    assert response.status_code == 400
    assert response.json()["detail"]["errorCode"] == "ERR_TASKS_002"


def test_update_task_state_allows_moving_out_of_completed(client, authenticate_as):
    user_id = _create_user(client)
    task_id = client.post(
        "/api/v1/tasks", json={"taskTitle": "Buy milk", "createdBy": user_id}
    ).json()["taskId"]
    authenticate_as(user_id)
    client.patch(f"/api/v1/tasks/{task_id}/state", json={"updatedBy": user_id, "taskState": "COMPLETED"})

    response = client.patch(
        f"/api/v1/tasks/{task_id}/state", json={"updatedBy": user_id, "taskState": "TODO"}
    )
    assert response.status_code == 200
    assert response.json()["taskState"] == "TODO"


def test_update_task_due_date(client, authenticate_as):
    user_id = _create_user(client)
    task_id = client.post(
        "/api/v1/tasks", json={"taskTitle": "Buy milk", "createdBy": user_id}
    ).json()["taskId"]

    authenticate_as(user_id)
    response = client.patch(
        f"/api/v1/tasks/{task_id}/due-date",
        json={"updatedBy": user_id, "taskDueDate": "2026-08-01T00:00:00Z"},
    )
    assert response.status_code == 200
    assert response.json()["taskDueDate"].startswith("2026-08-01")


def test_update_task_due_date_to_null_clears_it(client, authenticate_as):
    user_id = _create_user(client)
    task_id = client.post(
        "/api/v1/tasks", json={"taskTitle": "Buy milk", "createdBy": user_id}
    ).json()["taskId"]
    authenticate_as(user_id)
    client.patch(
        f"/api/v1/tasks/{task_id}/due-date",
        json={"updatedBy": user_id, "taskDueDate": "2026-08-01T00:00:00Z"},
    )

    response = client.patch(
        f"/api/v1/tasks/{task_id}/due-date",
        json={"updatedBy": user_id, "taskDueDate": None},
    )
    assert response.status_code == 200
    assert response.json()["taskDueDate"] is None


def test_update_task_state_same_state_returns_400(client, authenticate_as):
    user_id = _create_user(client)
    task_id = client.post(
        "/api/v1/tasks", json={"taskTitle": "Buy milk", "createdBy": user_id}
    ).json()["taskId"]

    authenticate_as(user_id)
    response = client.patch(
        f"/api/v1/tasks/{task_id}/state", json={"updatedBy": user_id, "taskState": "TODO"}
    )
    assert response.status_code == 400
    assert response.json()["detail"]["errorCode"] == "ERR_TASKS_002"


def test_list_my_tasks_returns_created_and_assigned(client, authenticate_as):
    owner_id = _create_user(client)
    other_id = _create_user(client, first_name="Bob", last_name="Smith")
    authenticate_as(owner_id)
    my_task_id = client.post(
        "/api/v1/tasks", json={"taskTitle": "My task", "createdBy": owner_id}
    ).json()["taskId"]
    client.post("/api/v1/tasks", json={"taskTitle": "Not mine", "createdBy": other_id})

    response = client.get("/api/v1/tasks")
    assert response.status_code == 200
    task_ids = [t["taskId"] for t in response.json()]
    assert my_task_id in task_ids
