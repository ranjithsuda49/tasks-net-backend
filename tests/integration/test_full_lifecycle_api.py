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


def test_full_cross_entity_lifecycle(client, authenticate_as):
    # 1. Create the owner user.
    owner_id = _create_user(client, authenticate_as, "owner", first_name="Ada", last_name="Lovelace")

    # 2. Create the member/assignee user.
    member_id = _create_user(client, authenticate_as, "member", first_name="Bob", last_name="Smith")

    # 3. Create a group with the owner as creator.
    group_id = _create_group(client, authenticate_as, owner_id)

    # Authenticate as the owner for every subsequent ownership-gated call in
    # this lifecycle (disassociate at the end also allows the creator, so no
    # further identity switch is needed).
    authenticate_as(owner_id)

    # 4. Associate the member to the group.
    associate_response = client.post(
        f"/api/v1/groups/{group_id}/members",
        json={"userId": member_id, "relationship": "Sibling"},
    )
    assert associate_response.status_code == 201
    assert associate_response.json()["userId"] == member_id
    assert associate_response.json()["groupId"] == group_id

    # 5. Create a task, created by the owner.
    task_id = _create_task(client, authenticate_as, owner_id)

    # 6. Assign the task to the member within the group.
    assign_response = client.post(
        f"/api/v1/groups/{group_id}/tasks/{task_id}/assignee", json={"assigneeId": member_id}
    )
    assert assign_response.status_code == 201
    assign_body = assign_response.json()
    assert assign_body["taskId"] == task_id
    assert assign_body["groupId"] == group_id
    assert assign_body["assigneeId"] == member_id

    # 7. Move the task through states: TODO -> IN-PROGRESS -> COMPLETED.
    in_progress_response = client.patch(
        f"/api/v1/tasks/{task_id}/state", json={"taskState": "IN-PROGRESS"}
    )
    assert in_progress_response.status_code == 200
    assert in_progress_response.json()["taskState"] == "IN-PROGRESS"

    completed_response = client.patch(
        f"/api/v1/tasks/{task_id}/state", json={"taskState": "COMPLETED"}
    )
    assert completed_response.status_code == 200
    assert completed_response.json()["taskState"] == "COMPLETED"

    # 8. Reassign the task back to the owner.
    reassign_response = client.patch(
        f"/api/v1/groups/{group_id}/tasks/{task_id}/assignee", json={"assigneeId": owner_id}
    )
    assert reassign_response.status_code == 200
    assert reassign_response.json()["assigneeId"] == owner_id

    # 9. Disassociate the member from the group.
    disassociate_response = client.delete(f"/api/v1/groups/{group_id}/members/{member_id}")
    assert disassociate_response.status_code == 204
