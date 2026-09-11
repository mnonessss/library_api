from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class BookingCreate(BaseModel):
    user_id: int
    book_id: int
    status: str = 'ACTIVE'


class BookingUpdate(BaseModel):
    status: str
    returned_at: Optional[datetime] = None


class BookingResponse(BaseModel):
    id: int
    user_id: int
    book_id: int
    status: str
    created_at: datetime
    returned_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class BookingWithBookResponse(BookingResponse):
    book_title: str | None = None


class BookingWithUserResponse(BookingResponse):
    user_name: str | None = None
