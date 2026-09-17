import enum

from app.database import Base

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.sql import func


class BookingStatus(str, enum.Enum):
    ACTIVE = 'ACTIVE'
    RETURNED = 'RETURNED'
    OVERDUE = 'OVERDUE'


class Booking(Base):
    __tablename__ = 'bookings'
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False,
                     index=True)
    book_id = Column(Integer, ForeignKey('books.id'), nullable=False,
                     index=True)
    status = Column(String, default=BookingStatus.ACTIVE, index=True)
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        primary_key=True,
        index=True,
    )
    returned_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index('idx_bookings_status_created_at', 'status', 'created_at'),
        Index('idx_bookings_user_created', 'user_id', created_at.desc()),
    )
