import uuid
from datetime import datetime, timezone
from typing import Optional

from app.exceptions import NotFoundError
from app.models.enums import UserStatus
from app.models.user import Name, User
from app.repositories.base import BaseRepository


class UserService:
    def __init__(self, repository: BaseRepository[User]):
        self._repository = repository

    def create_user(
        self,
        first_name: str,
        last_name: str,
        phone_num: Optional[str] = None,
        email_id: Optional[str] = None,
    ) -> User:
        now = datetime.now(timezone.utc)
        user = User(
            userId=str(uuid.uuid4()),
            name=Name(firstName=first_name, lastName=last_name),
            phoneNum=phone_num,
            emailId=email_id,
            userStatus=UserStatus.ACTIVE,
            createdAt=now,
            updatedAt=None,
        )
        return self._repository.add(user)

    def get_user(self, user_id: str) -> User:
        user = self._repository.get(user_id)
        if user is None:
            raise NotFoundError(f"User {user_id} not found")
        return user

    def update_user(
        self,
        user_id: str,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
        phone_num: Optional[str] = None,
        email_id: Optional[str] = None,
    ) -> User:
        user = self.get_user(user_id)
        updated = user.model_copy(
            update={
                "name": Name(
                    firstName=first_name if first_name is not None else user.name.firstName,
                    lastName=last_name if last_name is not None else user.name.lastName,
                ),
                "phoneNum": phone_num if phone_num is not None else user.phoneNum,
                "emailId": email_id if email_id is not None else user.emailId,
                "updatedAt": datetime.now(timezone.utc),
            }
        )
        return self._repository.update(updated)

    def set_status(self, user_id: str, status: UserStatus) -> User:
        user = self.get_user(user_id)
        updated = user.model_copy(
            update={"userStatus": status, "updatedAt": datetime.now(timezone.utc)}
        )
        return self._repository.update(updated)
