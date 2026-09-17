from app.repositories.user_repository import UserRepository

from sqlalchemy.orm import Session


class UserService:
    def __init__(self, db: Session):
        self.repo = UserRepository(db)

    def get_users(self, skip: int, limit: int):
        return self.repo.get_all(skip, limit)

    def count_users(self) -> int:
        return self.repo.count()

    def get_user(self, user_id: int):
        return self.repo.get_by_id(user_id)

    def create_user(self, name: str, email: str, user_id: int | None = None):
        return self.repo.create(name, email, user_id=user_id)

    def update_user(self, user_id: int, name: str, email: str):
        return self.repo.update(user_id, name, email)

    def delete_user(self, user_id: int) -> bool:
        return self.repo.delete(user_id)
