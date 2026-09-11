from app.repositories.book_repository import BookRepository

from sqlalchemy.orm import Session


class BookService:
    def __init__(self, db: Session):
        self.repo = BookRepository(db)

    def get_books(self, skip: int, limit: int):
        return self.repo.get_all(skip, limit)

    def get_book(self, book_id: int):
        return self.repo.get_by_id(book_id)

    def create_book(self, title: str, author: str, total_copies: int):
        return self.repo.create(title, author, total_copies)

    def update_book(self, book_id: int, title: str, author: str,
                    total_copies: int):
        return self.repo.update(book_id, title, author, total_copies)

    def delete_book(self, book_id: int) -> bool:
        return self.repo.delete(book_id)

    def get_books_with_categories(self, search: str | None, skip: int,
                                  limit: int):
        return self.repo.get_books_with_categories(search, skip, limit)

    def get_top_popular_books(self, limit: int = 5):
        return self.repo.get_top_popular_books(limit)
