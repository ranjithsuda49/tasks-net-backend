from fastapi import APIRouter, Depends, HTTPException, status

from app.dependencies import get_user_group_service
from app.exceptions import BadRequestError, NotFoundError
from app.schemas.errors import ErrorDetail
from app.schemas.user_group import UserGroupAssociateRequest, UserGroupResponse
from app.services.user_group_service import UserGroupService

router = APIRouter(prefix="/api/v1/groups", tags=["user-group"])


@router.post(
    "/{group_id}/members", response_model=UserGroupResponse, status_code=status.HTTP_201_CREATED
)
def associate_user(
    group_id: str,
    payload: UserGroupAssociateRequest,
    service: UserGroupService = Depends(get_user_group_service),
) -> UserGroupResponse:
    try:
        relationship = service.associate(payload.userId, group_id, payload.relationship)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except BadRequestError as exc:
        raise HTTPException(
            status_code=exc.http_code,
            detail=ErrorDetail(errorCode=exc.error_code, message=exc.message).model_dump(),
        ) from exc
    return UserGroupResponse(**relationship.model_dump())


@router.delete("/{group_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def disassociate_user(
    group_id: str, user_id: str, service: UserGroupService = Depends(get_user_group_service)
) -> None:
    try:
        service.disassociate(user_id, group_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
