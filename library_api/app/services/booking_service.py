from datetime import date

from app.repositories.booking_repository import BookingRepository

from sqlalchemy.orm import Session


class BookingService:
    def __init__(self, db: Session):
        self.repo = BookingRepository(db)

    def get_all_bookings(self, skip: int, limit: int, status: str | None = None,
                         sort: str = 'created_at', from_date: date | None = None,
                         to_date: date | None = None):
        return self.repo.get_all_bookings(
            skip, limit, status, sort, from_date, to_date
        )

    def get_booking_by_id(self, booking_id: int):
        return self.repo.get_booking_by_id(booking_id)

    def create_booking(self, user_id: int, book_id: int,
                       status: str = 'ACTIVE'):
        return self.repo.create_booking(user_id, book_id, status)

    def get_bookings_by_user_id(self, user_id: int):
        return self.repo.get_user_bookings_with_books(user_id)

    def get_bookings_by_book_id(self, book_id: int):
        return self.repo.get_bookings_by_book_id(book_id)

    def update_booking(self, booking_id: int, status: str, returned_at=None):
        return self.repo.update_booking(booking_id, status, returned_at)

    def delete_booking(self, booking_id: int) -> bool:
        return self.repo.delete_booking(booking_id)

    def get_bookings_in_range(self, start_date: str, end_date: str):
        return self.repo.get_bookings_in_range(start_date, end_date)
