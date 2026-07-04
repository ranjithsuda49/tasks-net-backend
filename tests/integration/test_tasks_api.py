def _create_user(client, first_name="Ada", last_name="Lovelace"):
    return client.post(
        "/api/v1/users", json={"firstName": first_name, "lastName": last_name}
    ).json()["userId"]


def test_create_and_fetch_task(client):
    user_id = _create_user(client)
    create_response = client.post(
        "/api/v1/tasks", json={"taskTitle": "Buy milk", "createdBy": user_id}
    )
    assert create_response.status_code == 201
    body = create_response.json()
    assert body["taskState"] == "TODO"
    task_id = body["taskId"]

    fetch_response = client.get(f"/api/v1/tasks/{task_id}")
    assert fetch_response.status_code == 200
    assert fetch_response.json()["taskId"] == task_id


def test_create_task_unknown_user_returns_404(client):
    response = client.post("/api/v1/tasks", json={"taskTitle": "Buy milk", "createdBy": "unknown"})
    assert response.status_code == 404


def test_update_task_meta(client):
    user_id = _create_user(client)
    task_id = client.post(
        "/api/v1/tasks", json={"taskTitle": "Buy milk", "createdBy": user_id}
    ).json()["taskId"]

    response = client.patch(
        f"/api/v1/tasks/{task_id}", json={"updatedBy": user_id, "taskTitle": "Buy oat milk"}
    )
    assert response.status_code == 200
    assert response.json()["taskTitle"] == "Buy oat milk"


def test_update_task_state(client):
    user_id = _create_user(client)
    task_id = client.post(
        "/api/v1/tasks", json={"taskTitle": "Buy milk", "createdBy": user_id}
    ).json()["taskId"]

    response = client.patch(
        f"/api/v1/tasks/{task_id}/state", json={"updatedBy": user_id, "taskState": "IN-PROGRESS"}
    )
    assert response.status_code == 200
    assert response.json()["taskState"] == "IN-PROGRESS"


def test_update_task_state_already_completed_returns_400(client):
    user_id = _create_user(client)
    task_id = client.post(
        "/api/v1/tasks", json={"taskTitle": "Buy milk", "createdBy": user_id}
    ).json()["taskId"]
    client.patch(f"/api/v1/tasks/{task_id}/state", json={"updatedBy": user_id, "taskState": "COMPLETED"})

    response = client.patch(
        f"/api/v1/tasks/{task_id}/state", json={"updatedBy": user_id, "taskState": "COMPLETED"}
    )
    assert response.status_code == 400
    assert response.json()["detail"]["errorCode"] == "ERR_TASKS_002"


def test_update_task_state_allows_moving_out_of_completed(client):
    user_id = _create_user(client)
    task_id = client.post(
        "/api/v1/tasks", json={"taskTitle": "Buy milk", "createdBy": user_id}
    ).json()["taskId"]
    client.patch(f"/api/v1/tasks/{task_id}/state", json={"updatedBy": user_id, "taskState": "COMPLETED"})

    response = client.patch(
        f"/api/v1/tasks/{task_id}/state", json={"updatedBy": user_id, "taskState": "TODO"}
    )
    assert response.status_code == 200
    assert response.json()["taskState"] == "TODO"


def test_update_task_due_date(client):
    user_id = _create_user(client)
    task_id = client.post(
        "/api/v1/tasks", json={"taskTitle": "Buy milk", "createdBy": user_id}
    ).json()["taskId"]

    response = client.patch(
        f"/api/v1/tasks/{task_id}/due-date",
        json={"updatedBy": user_id, "taskDueDate": "2026-08-01T00:00:00Z"},
    )
    assert response.status_code == 200
    assert response.json()["taskDueDate"].startswith("2026-08-01")


def test_update_task_due_date_to_null_clears_it(client):
    user_id = _create_user(client)
    task_id = client.post(
        "/api/v1/tasks", json={"taskTitle": "Buy milk", "createdBy": user_id}
    ).json()["taskId"]
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
