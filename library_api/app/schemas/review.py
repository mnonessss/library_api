from datetime import datetime

from pydantic import BaseModel, Field


class ReviewCreate(BaseModel):
    user_id: int
    book_id: int
    rating: int = Field(ge=1, le=5)
    comment: str | None = None


class ReviewUpdate(BaseModel):
    rating: int = Field(ge=1, le=5)
    comment: str | None = None


class ReviewResponse(BaseModel):
    id: int
    user_id: int
    book_id: int
    rating: int
    comment: str | None = None
    created_at: datetime

    class Config:
        from_attributes = True


class ReviewWithUserResponse(ReviewResponse):
    user_name: str | None = None


class ReviewWithBookResponse(ReviewResponse):
    book_title: str | None = None


class BookRatingStats(BaseModel):
    book_id: int
    book_title: str
    review_count: int
    average_rating: float

    class Config:
        from_attributes = True
