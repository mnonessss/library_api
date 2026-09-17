from app.database import get_db, get_db_replica
from app.schemas.book import (
    BookCreate,
    BookResponse,
    BookUpdate,
    BookWithCategoryResponse,
    PopularBookResponse,
)
from app.schemas.booking import BookingWithUserResponse
from app.schemas.review import ReviewWithUserResponse
from app.services.book_service import BookService
from app.services.booking_service import BookingService
from app.services.review_service import ReviewService

from fastapi import APIRouter, Depends, HTTPException, Query

from sqlalchemy.orm import Session


router = APIRouter(prefix='/api/books', tags=['books'])


@router.get('/popular', response_model=list[PopularBookResponse])
def get_popular_books(
    limit: int = Query(5, ge=1, le=50),
    db: Session = Depends(get_db_replica),
):
    service = BookService(db)
    return service.get_top_popular_books(limit)


# Каталог книг — только чтение, поэтому сессия Replica (get_db_replica).
@router.get('/', response_model=list[BookResponse | BookWithCategoryResponse])
def get_books(
    skip: int = 0,
    limit: int = 20,
    search: str | None = Query(None, description='Поиск по названию книги'),
    db: Session = Depends(get_db_replica),
):
    service = BookService(db)
    if search is not None:
        return service.get_books_with_categories(search, skip, limit)
    return service.get_books(skip, limit)


@router.get('/{book_id}', response_model=BookResponse)
def get_book(book_id: int, db: Session = Depends(get_db_replica)):
    service = BookService(db)
    book = service.get_book(book_id)

    if not book:
        raise HTTPException(status_code=404, detail='Book not found')

    return book


@router.get('/{book_id}/bookings', response_model=list[BookingWithUserResponse])
def get_book_bookings(book_id: int, db: Session = Depends(get_db)):
    service = BookingService(db)
    return service.get_bookings_by_book_id(book_id)


@router.get('/{book_id}/reviews', response_model=list[ReviewWithUserResponse])
def get_book_reviews(
    book_id: int,
    skip: int = 0,
    limit: int = 20,
    db: Session = Depends(get_db),
):
    service = ReviewService(db)
    return service.get_reviews_by_book_id(book_id, skip, limit)


@router.post('/', response_model=BookResponse, status_code=201)
def create_book(book: BookCreate, db: Session = Depends(get_db)):
    service = BookService(db)
    return service.create_book(book.title, book.author, book.total_copies)


@router.put('/{book_id}', response_model=BookResponse)
def update_book(book_id: int, book: BookUpdate, db: Session = Depends(get_db)):
    service = BookService(db)
    updated = service.update_book(
        book_id, book.title, book.author, book.total_copies
    )
    if not updated:
        raise HTTPException(status_code=404, detail='Book not found')
    return updated


@router.delete('/{book_id}', status_code=204)
def delete_book(book_id: int, db: Session = Depends(get_db)):
    service = BookService(db)
    if not service.delete_book(book_id):
        raise HTTPException(status_code=404, detail='Book not found')
    return None
