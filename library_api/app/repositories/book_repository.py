from sqlalchemy import text
from sqlalchemy.orm import Session


class BookRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_all(self, skip: int = 0, limit: int = 20):
        query = text('SELECT id, title, \
                    author, total_copies, created_at \
                    FROM books ORDER BY id LIMIT :limit OFFSET :skip')
        return (
            self.db.execute(query, {'limit': limit, 'skip': skip}).fetchall()
        )

    def get_by_id(self, book_id: int):
        query = text('SELECT id, title,  \
                    author, total_copies, created_at \
                    FROM books WHERE id = :book_id')
        return self.db.execute(query, {'book_id': book_id}).fetchone()

    def create(self, title: str, author: str, total_copies: int):
        query = text("""
            INSERT INTO books (title, author, total_copies)
            VALUES (:title, :author, :total_copies)
            RETURNING id, title, author, total_copies, created_at
        """)
        result = self.db.execute(query, {'title': title, 'author': author,
                                         'total_copies': total_copies})
        self.db.commit()
        return result.fetchone()

    def update(self, book_id: int, title: str, author: str, total_copies: int):
        query = text("""
            UPDATE books
            SET title = :title, author = :author, total_copies = :total_copies
            WHERE id = :book_id
            RETURNING id, title, author, total_copies, created_at
        """)
        result = self.db.execute(
            query,
            {
                'book_id': book_id,
                'title': title,
                'author': author,
                'total_copies': total_copies,
            },
        )
        self.db.commit()
        return result.fetchone()

    def delete(self, book_id: int) -> bool:
        if not self.get_by_id(book_id):
            return False

        self.db.execute(
            text('DELETE FROM reviews WHERE book_id = :book_id'),
            {'book_id': book_id},
        )
        self.db.execute(
            text('DELETE FROM bookings WHERE book_id = :book_id'),
            {'book_id': book_id},
        )
        self.db.execute(
            text('DELETE FROM book_categories WHERE book_id = :book_id'),
            {'book_id': book_id},
        )
        result = self.db.execute(
            text('DELETE FROM books WHERE id = :book_id RETURNING id'),
            {'book_id': book_id},
        )
        self.db.commit()
        return result.fetchone() is not None

    def get_books_with_categories(self, search: str | None = None,
                                  skip: int = 0, limit: int = 20):
        if search:
            query = text("""
                SELECT DISTINCT
                    books.id,
                    books.title,
                    books.author,
                    books.total_copies,
                    books.created_at,
                    categories.name as category_name
                FROM books
                LEFT JOIN book_categories ON books.id = book_categories.book_id
                LEFT JOIN
                    categories ON book_categories.category_id = categories.id
                WHERE books.title ILIKE :search
                ORDER BY books.created_at DESC
                LIMIT :limit OFFSET :skip
            """)
            params = {'search': f'%{search}%', 'limit': limit, 'skip': skip}
        else:
            query = text("""
                SELECT DISTINCT
                    books.id,
                    books.title,
                    books.author,
                    books.total_copies,
                    books.created_at,
                    categories.name as category_name
                FROM books
                LEFT JOIN book_categories ON books.id = book_categories.book_id
                LEFT JOIN
                    categories ON book_categories.category_id = categories.id
                ORDER BY books.created_at DESC
                LIMIT :limit OFFSET :skip
            """)
            params = {'limit': limit, 'skip': skip}

        return self.db.execute(query, params).fetchall()

    def get_top_popular_books(self, limit: int = 5):
        query = text("""
            SELECT
                books.id,
                books.title,
                books.author,
                COUNT(bookings.id) as booking_count
            FROM bookings
            JOIN books ON bookings.book_id = books.id
            GROUP BY books.id, books.title, books.author
            ORDER BY booking_count DESC
            LIMIT :limit
        """)
        return self.db.execute(query, {'limit': limit}).fetchall()
