from datetime import datetime

from pydantic import BaseModel


class BookCreate(BaseModel):
    title: str
    author: str
    total_copies: int = 1


class BookUpdate(BaseModel):
    title: str
    author: str
    total_copies: int = 1


class BookWithCategoryResponse(BaseModel):
    id: int
    title: str
    author: str
    total_copies: int
    created_at: datetime
    category_name: str | None = None

    class Config:
        from_attributes = True


class PopularBookResponse(BaseModel):
    id: int
    title: str
    author: str
    booking_count: int

    class Config:
        from_attributes = True


class BookResponse(BaseModel):
    id: int
    title: str
    author: str
    total_copies: int
    created_at: datetime

    class Config:
        from_attributes = True
