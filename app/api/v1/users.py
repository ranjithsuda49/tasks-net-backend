from fastapi import APIRouter, Depends, HTTPException, status

from app.dependencies import get_user_service
from app.exceptions import NotFoundError
from app.models.user import User
from app.schemas.user import (
    NameSchema,
    UserCreateRequest,
    UserResponse,
    UserStatusUpdateRequest,
    UserUpdateRequest,
)
from app.services.user_service import UserService

router = APIRouter(prefix="/api/v1/users", tags=["users"])


def _to_response(user: User) -> UserResponse:
    return UserResponse(
        userId=user.userId,
        name=NameSchema(firstName=user.name.firstName, lastName=user.name.lastName),
        phoneNum=user.phoneNum,
        emailId=user.emailId,
        userStatus=user.userStatus,
        createdAt=user.createdAt,
        updatedAt=user.updatedAt,
    )


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreateRequest, service: UserService = Depends(get_user_service)
) -> UserResponse:
    user = service.create_user(
        first_name=payload.firstName,
        last_name=payload.lastName,
        phone_num=payload.phoneNum,
        email_id=payload.emailId,
    )
    return _to_response(user)


@router.get(
    "/{user_id}",
    response_model=UserResponse,
    responses={404: {"description": "User not found"}},
)
def get_user(user_id: str, service: UserService = Depends(get_user_service)) -> UserResponse:
    try:
        user = service.get_user(user_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _to_response(user)


@router.patch(
    "/{user_id}",
    response_model=UserResponse,
    responses={404: {"description": "User not found"}},
)
def update_user(
    user_id: str, payload: UserUpdateRequest, service: UserService = Depends(get_user_service)
) -> UserResponse:
    try:
        user = service.update_user(
            user_id,
            first_name=payload.firstName,
            last_name=payload.lastName,
            phone_num=payload.phoneNum,
            email_id=payload.emailId,
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _to_response(user)


@router.patch(
    "/{user_id}/status",
    response_model=UserResponse,
    responses={404: {"description": "User not found"}},
)
def update_user_status(
    user_id: str,
    payload: UserStatusUpdateRequest,
    service: UserService = Depends(get_user_service),
) -> UserResponse:
    try:
        user = service.set_status(user_id, payload.userStatus)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _to_response(user)
