from sqlalchemy import text
from sqlalchemy.orm import Session


class UserRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_all(self, skip: int = 0, limit: int = 20):
        query = text('SELECT id, name, \
                     email, created_at \
                     FROM users ORDER BY id LIMIT :limit OFFSET :skip')
        return (
            self.db.execute(query, {'limit': limit, 'skip': skip}).fetchall()
            )

    def get_by_id(self, user_id: int):
        query = text('SELECT id, name, \
                     email, created_at FROM users WHERE id = :user_id')
        return self.db.execute(query, {'user_id': user_id}).fetchone()

    def create(self, name: str, email: str):
        query = text("""
            INSERT INTO users (name, email) VALUES (:name, :email)
            RETURNING id, name, email, created_at
        """)
        result = self.db.execute(query, {'name': name, 'email': email})
        self.db.commit()
        return result.fetchone()

    def update(self, user_id: int, name: str, email: str):
        query = text("""
            UPDATE users
            SET name = :name, email = :email
            WHERE id = :user_id
            RETURNING id, name, email, created_at
        """)
        result = self.db.execute(
            query, {'user_id': user_id, 'name': name, 'email': email}
        )
        self.db.commit()
        return result.fetchone()

    def delete(self, user_id: int) -> bool:
        if not self.get_by_id(user_id):
            return False

        self.db.execute(
            text('DELETE FROM reviews WHERE user_id = :user_id'),
            {'user_id': user_id},
        )
        self.db.execute(
            text('DELETE FROM bookings WHERE user_id = :user_id'),
            {'user_id': user_id},
        )
        result = self.db.execute(
            text('DELETE FROM users WHERE id = :user_id RETURNING id'),
            {'user_id': user_id},
        )
        self.db.commit()
        return result.fetchone() is not None
