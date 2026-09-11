from datetime import date

from app.database import get_db
from app.schemas.booking import BookingCreate, BookingResponse, BookingUpdate
from app.services.booking_service import BookingService

from fastapi import APIRouter, Depends, HTTPException, Query

from sqlalchemy.orm import Session


router = APIRouter(prefix='/api/bookings', tags=['bookings'])

VALID_STATUSES = {'ACTIVE', 'RETURNED', 'OVERDUE'}
VALID_SORTS = {'created_at', '-created_at'}


@router.get('/', response_model=list[BookingResponse])
def get_bookings(
    page: int = Query(1, ge=1, description='Номер страницы'),
    page_size: int = Query(20, ge=1, le=100,
                           description='Количество записей на странице'),
    status: str | None = Query(
        None, description='Фильтр: ACTIVE, RETURNED или OVERDUE'
    ),
    from_date: date | None = Query(
        None, description='Дата начала, формат YYYY-MM-DD (например 2026-01-01)'
    ),
    to_date: date | None = Query(
        None, description='Дата конца, формат YYYY-MM-DD (например 2026-12-31)'
    ),
    sort: str = Query('created_at', description='created_at или -created_at'),
    db: Session = Depends(get_db),
):
    if status is not None and status not in VALID_STATUSES:
        raise HTTPException(
            status_code=422,
            detail=f'Invalid status. Allowed: {", ".join(sorted(VALID_STATUSES))}',
        )
    if sort not in VALID_SORTS:
        raise HTTPException(
            status_code=422,
            detail=f'Invalid sort. Allowed: {", ".join(sorted(VALID_SORTS))}',
        )
    if from_date and to_date and from_date > to_date:
        raise HTTPException(
            status_code=422,
            detail='from_date must be less than or equal to to_date',
        )

    service = BookingService(db)
    skip = (page - 1) * page_size

    return service.get_all_bookings(
        skip=skip,
        limit=page_size,
        status=status,
        sort=sort,
        from_date=from_date,
        to_date=to_date,
    )


@router.get('/{booking_id}', response_model=BookingResponse)
def get_booking(booking_id: int, db: Session = Depends(get_db)):
    service = BookingService(db)
    booking = service.get_booking_by_id(booking_id)

    if not booking:
        raise HTTPException(status_code=404, detail='Booking not found')

    return booking


@router.post('/', response_model=BookingResponse, status_code=201)
def create_booking(booking: BookingCreate, db: Session = Depends(get_db)):
    service = BookingService(db)

    if booking.status not in ['ACTIVE', 'RETURNED', 'OVERDUE']:
        raise HTTPException(status_code=400, detail='Invalid status')

    return service.create_booking(
        user_id=booking.user_id,
        book_id=booking.book_id,
        status=booking.status,
    )


@router.put('/{booking_id}', response_model=BookingResponse)
def update_booking(
    booking_id: int,
    update_data: BookingUpdate,
    db: Session = Depends(get_db),
):
    service = BookingService(db)
    booking = service.update_booking(
        booking_id, update_data.status, update_data.returned_at
    )

    if not booking:
        raise HTTPException(status_code=404, detail='Booking not found')

    return booking


@router.delete('/{booking_id}', status_code=204)
def delete_booking(booking_id: int, db: Session = Depends(get_db)):
    service = BookingService(db)
    if not service.delete_booking(booking_id):
        raise HTTPException(status_code=404, detail='Booking not found')
    return None
