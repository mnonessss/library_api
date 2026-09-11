from sqlalchemy import text
from sqlalchemy.orm import Session


class ReviewRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_all(self, skip: int = 0, limit: int = 20):
        query = text("""
            SELECT id, user_id, book_id, rating, comment, created_at
            FROM reviews
            ORDER BY created_at DESC
            LIMIT :limit OFFSET :skip
        """)
        return self.db.execute(query, {'limit': limit, 'skip': skip}).fetchall()

    def get_by_id(self, review_id: int):
        query = text("""
            SELECT id, user_id, book_id, rating, comment, created_at
            FROM reviews
            WHERE id = :review_id
        """)
        return self.db.execute(query, {'review_id': review_id}).fetchone()

    def create(self, user_id: int, book_id: int, rating: int,
               comment: str | None):
        query = text("""
            INSERT INTO reviews (user_id, book_id, rating, comment)
            VALUES (:user_id, :book_id, :rating, :comment)
            RETURNING id, user_id, book_id, rating, comment, created_at
        """)
        result = self.db.execute(
            query,
            {
                'user_id': user_id,
                'book_id': book_id,
                'rating': rating,
                'comment': comment,
            },
        )
        self.db.commit()
        return result.fetchone()

    def update(self, review_id: int, rating: int, comment: str | None):
        query = text("""
            UPDATE reviews
            SET rating = :rating, comment = :comment
            WHERE id = :review_id
            RETURNING id, user_id, book_id, rating, comment, created_at
        """)
        result = self.db.execute(
            query,
            {'review_id': review_id, 'rating': rating, 'comment': comment},
        )
        self.db.commit()
        return result.fetchone()

    def delete(self, review_id: int) -> bool:
        query = text('DELETE FROM reviews WHERE id = :review_id RETURNING id')
        result = self.db.execute(query, {'review_id': review_id})
        self.db.commit()
        return result.fetchone() is not None

    def get_by_book_id(self, book_id: int, skip: int = 0, limit: int = 20):
        query = text("""
            SELECT
                reviews.id,
                reviews.user_id,
                reviews.book_id,
                reviews.rating,
                reviews.comment,
                reviews.created_at,
                users.name as user_name
            FROM reviews
            JOIN users ON reviews.user_id = users.id
            WHERE reviews.book_id = :book_id
            ORDER BY reviews.created_at DESC
            LIMIT :limit OFFSET :skip
        """)
        return self.db.execute(
            query, {'book_id': book_id, 'limit': limit, 'skip': skip}
        ).fetchall()

    def get_by_user_id(self, user_id: int, skip: int = 0, limit: int = 20):
        query = text("""
            SELECT
                reviews.id,
                reviews.user_id,
                reviews.book_id,
                reviews.rating,
                reviews.comment,
                reviews.created_at,
                books.title as book_title
            FROM reviews
            JOIN books ON reviews.book_id = books.id
            WHERE reviews.user_id = :user_id
            ORDER BY reviews.created_at DESC
            LIMIT :limit OFFSET :skip
        """)
        return self.db.execute(
            query, {'user_id': user_id, 'limit': limit, 'skip': skip}
        ).fetchall()

    def get_average_ratings_by_book(self, limit: int = 10):
        query = text("""
            SELECT
                books.id as book_id,
                books.title as book_title,
                COUNT(reviews.id) as review_count,
                ROUND(AVG(reviews.rating)::numeric, 2) as average_rating
            FROM reviews
            JOIN books ON reviews.book_id = books.id
            GROUP BY books.id, books.title
            ORDER BY average_rating DESC, review_count DESC
            LIMIT :limit
        """)
        return self.db.execute(query, {'limit': limit}).fetchall()
