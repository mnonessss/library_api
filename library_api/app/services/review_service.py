from app.repositories.review_repository import ReviewRepository

from sqlalchemy.orm import Session


class ReviewService:
    def __init__(self, db: Session):
        self.repo = ReviewRepository(db)

    def get_reviews(self, skip: int, limit: int):
        return self.repo.get_all(skip, limit)

    def get_review(self, review_id: int):
        return self.repo.get_by_id(review_id)

    def create_review(self, user_id: int, book_id: int, rating: int,
                      comment: str | None):
        return self.repo.create(user_id, book_id, rating, comment)

    def update_review(self, review_id: int, rating: int, comment: str | None):
        return self.repo.update(review_id, rating, comment)

    def delete_review(self, review_id: int) -> bool:
        return self.repo.delete(review_id)

    def get_reviews_by_book_id(self, book_id: int, skip: int, limit: int):
        return self.repo.get_by_book_id(book_id, skip, limit)

    def get_reviews_by_user_id(self, user_id: int, skip: int, limit: int):
        return self.repo.get_by_user_id(user_id, skip, limit)

    def get_average_ratings_by_book(self, limit: int = 10):
        return self.repo.get_average_ratings_by_book(limit)
