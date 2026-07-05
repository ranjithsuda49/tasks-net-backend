from fastapi import APIRouter, Depends, HTTPException, status

from app.auth import verify_firebase_token
from app.dependencies import get_user_group_service
from app.exceptions import BadRequestError, ForbiddenError, NotFoundError
from app.schemas.errors import BadRequestResponse, ErrorDetail
from app.schemas.user_group import UserGroupAssociateRequest, UserGroupResponse
from app.services.user_group_service import UserGroupService

router = APIRouter(prefix="/api/v1/groups", tags=["user-group"])


@router.post(
    "/{group_id}/members",
    response_model=UserGroupResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        404: {"description": "User or Group not found"},
        400: {"model": BadRequestResponse, "description": "User is already associated with this group"},
        403: {"description": "Not authorized"},
    },
)
def associate_user(
    group_id: str,
    payload: UserGroupAssociateRequest,
    current_user_id: str = Depends(verify_firebase_token),
    service: UserGroupService = Depends(get_user_group_service),
) -> UserGroupResponse:
    try:
        relationship = service.associate(
            payload.userId, group_id, payload.relationship, current_user_id=current_user_id
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except BadRequestError as exc:
        raise HTTPException(
            status_code=exc.http_code,
            detail=ErrorDetail(errorCode=exc.error_code, message=exc.message).model_dump(),
        ) from exc
    except ForbiddenError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return UserGroupResponse(**relationship.model_dump())


@router.get(
    "/{group_id}/members",
    response_model=list[UserGroupResponse],
    responses={404: {"description": "Group not found"}, 403: {"description": "Not authorized"}},
)
def get_group_members(
    group_id: str,
    current_user_id: str = Depends(verify_firebase_token),
    service: UserGroupService = Depends(get_user_group_service),
) -> list[UserGroupResponse]:
    try:
        relationships = service.list_by_group(group_id, current_user_id=current_user_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ForbiddenError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return [UserGroupResponse(**r.model_dump()) for r in relationships]


@router.delete(
    "/{group_id}/members/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        404: {"description": "User is not associated with this group"},
        400: {"model": BadRequestResponse, "description": "Group creator cannot be de-associated"},
        403: {"description": "Not authorized"},
    },
)
def disassociate_user(
    group_id: str,
    user_id: str,
    current_user_id: str = Depends(verify_firebase_token),
    service: UserGroupService = Depends(get_user_group_service),
) -> None:
    try:
        service.disassociate(user_id, group_id, current_user_id=current_user_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except BadRequestError as exc:
        raise HTTPException(
            status_code=exc.http_code,
            detail=ErrorDetail(errorCode=exc.error_code, message=exc.message).model_dump(),
        ) from exc
    except ForbiddenError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
