from datetime import date, timedelta

from sqlalchemy import text
from sqlalchemy.orm import Session


class BookingRepository:
    def __init__(self, db: Session):
        self.db = db

    # 1. JOIN-запрос №1: Получить бронирования пользователя с деталями книги
    def get_user_bookings_with_books(self, user_id: int, skip: int = 0,
                                     limit: int = 20):
        query = text("""
            SELECT
                bookings.id,
                bookings.user_id,
                bookings.book_id,
                bookings.status,
                bookings.created_at,
                bookings.returned_at,
                books.title as book_title
            FROM bookings
            JOIN books ON bookings.book_id = books.id
            WHERE bookings.user_id = :user_id
            ORDER BY bookings.created_at DESC
            LIMIT :limit OFFSET :skip
        """)

        result = self.db.execute(
            query,
            {'user_id': user_id, 'limit': limit, 'skip': skip}
        )
        return result.fetchall()

    # 2. JOIN-запрос №2: Бронирования книги с данными пользователя
    def get_bookings_by_book_id(self, book_id: int, skip: int = 0,
                                limit: int = 20):
        query = text("""
            SELECT
                bookings.id,
                bookings.user_id,
                bookings.book_id,
                bookings.status,
                bookings.created_at,
                bookings.returned_at,
                users.name as user_name
            FROM bookings
            JOIN users ON bookings.user_id = users.id
            WHERE bookings.book_id = :book_id
            ORDER BY bookings.created_at DESC
            LIMIT :limit OFFSET :skip
        """)
        return self.db.execute(
            query, {'book_id': book_id, 'limit': limit, 'skip': skip}
        ).fetchall()

    # 3. Фильтрация по диапазону дат (для будущего партиционирования)
    def get_bookings_in_range(self, start_date: str, end_date: str):
        query = text("""
            SELECT
                id,
                user_id,
                book_id,
                status,
                created_at,
                returned_at
            FROM bookings
            WHERE created_at BETWEEN :start_date AND :end_date
            ORDER BY created_at DESC
        """)

        result = self.db.execute(
            query,
            {'start_date': start_date, 'end_date': end_date}
        )
        return result.fetchall()

    def get_all_bookings(self, skip: int = 0, limit: int = 20,
                         status: str | None = None,
                         sort: str = 'created_at',
                         from_date: date | None = None,
                         to_date: date | None = None):
        order_clause = 'DESC' if sort == '-created_at' else 'ASC'
        conditions = []
        params = {'limit': limit, 'skip': skip}

        if status:
            conditions.append('status = :status')
            params['status'] = status
        if from_date:
            conditions.append('created_at >= :from_date')
            params['from_date'] = from_date
        if to_date:
            conditions.append('created_at < :to_date_end')
            params['to_date_end'] = to_date + timedelta(days=1)

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ''
        query = text(f"""
            SELECT
                id,
                user_id,
                book_id,
                status,
                created_at,
                returned_at
            FROM bookings
            {where_clause}
            ORDER BY created_at {order_clause}
            LIMIT :limit OFFSET :skip
        """)

        return self.db.execute(query, params).fetchall()

    # 6. Создать бронирование
    def create_booking(self, user_id: int, book_id: int, status='ACTIVE'):
        query = text("""
            INSERT INTO bookings (user_id, book_id, status, created_at)
            VALUES (:user_id, :book_id, :status, NOW())
            RETURNING id, user_id, book_id, status, created_at, returned_at
        """)

        result = self.db.execute(
            query,
            {'user_id': user_id, 'book_id': book_id, 'status': status}
        )
        self.db.commit()
        return result.fetchone()

    # 7. Получить бронирование по ID
    def get_booking_by_id(self, booking_id: int):
        query = text("""
            SELECT
                id,
                user_id,
                book_id,
                status,
                created_at,
                returned_at
            FROM bookings
            WHERE id = :booking_id
        """)

        result = self.db.execute(query, {'booking_id': booking_id})
        return result.fetchone()

    def update_booking(self, booking_id: int, status: str,
                       returned_at=None):
        query = text("""
            UPDATE bookings
            SET status = :status, returned_at = :returned_at
            WHERE id = :booking_id
            RETURNING id, user_id, book_id, status, created_at, returned_at
        """)
        result = self.db.execute(
            query,
            {
                'booking_id': booking_id,
                'status': status,
                'returned_at': returned_at,
            },
        )
        self.db.commit()
        return result.fetchone()

    def delete_booking(self, booking_id: int) -> bool:
        query = text(
            'DELETE FROM bookings WHERE id = :booking_id RETURNING id'
        )
        result = self.db.execute(query, {'booking_id': booking_id})
        self.db.commit()
        return result.fetchone() is not None
