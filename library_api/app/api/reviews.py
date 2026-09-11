from app.database import get_db
from app.schemas.review import (
    BookRatingStats,
    ReviewCreate,
    ReviewResponse,
    ReviewUpdate,
    ReviewWithBookResponse,
    ReviewWithUserResponse,
)
from app.services.review_service import ReviewService

from fastapi import APIRouter, Depends, HTTPException, Query

from sqlalchemy.orm import Session


router = APIRouter(prefix='/api/reviews', tags=['reviews'])


@router.get('/stats/ratings', response_model=list[BookRatingStats])
def get_book_rating_stats(
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
):
    service = ReviewService(db)
    return service.get_average_ratings_by_book(limit)


@router.get('/', response_model=list[ReviewResponse])
def get_reviews(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    service = ReviewService(db)
    skip = (page - 1) * page_size
    return service.get_reviews(skip, page_size)


@router.get('/{review_id}', response_model=ReviewResponse)
def get_review(review_id: int, db: Session = Depends(get_db)):
    service = ReviewService(db)
    review = service.get_review(review_id)
    if not review:
        raise HTTPException(status_code=404, detail='Review not found')
    return review


@router.post('/', response_model=ReviewResponse, status_code=201)
def create_review(review: ReviewCreate, db: Session = Depends(get_db)):
    service = ReviewService(db)
    return service.create_review(
        review.user_id, review.book_id, review.rating, review.comment
    )


@router.put('/{review_id}', response_model=ReviewResponse)
def update_review(
    review_id: int,
    review: ReviewUpdate,
    db: Session = Depends(get_db),
):
    service = ReviewService(db)
    updated = service.update_review(review_id, review.rating, review.comment)
    if not updated:
        raise HTTPException(status_code=404, detail='Review not found')
    return updated


@router.delete('/{review_id}', status_code=204)
def delete_review(review_id: int, db: Session = Depends(get_db)):
    service = ReviewService(db)
    if not service.delete_review(review_id):
        raise HTTPException(status_code=404, detail='Review not found')
    return None
