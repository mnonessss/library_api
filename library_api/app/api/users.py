from app.database import get_db, get_db_replica
from app.schemas.booking import BookingWithBookResponse
from app.schemas.review import ReviewWithBookResponse
from app.schemas.user import UserCountResponse, UserCreate, UserResponse, UserUpdate
from app.services.booking_service import BookingService
from app.services.review_service import ReviewService
from app.services.user_service import UserService
from app.sharding.pool import get_db_for_user, sharding_enabled
from app.sharding import users as sharded_users

from fastapi import APIRouter, Depends, HTTPException

from sqlalchemy.orm import Session


router = APIRouter(prefix='/api/users', tags=['users'])


@router.get('/', response_model=list[UserResponse])
def get_users(
    skip: int = 0,
    limit: int = 20,
    db: Session = Depends(get_db_replica),
):
    if sharding_enabled():
        return sharded_users.list_users(skip, limit)
    service = UserService(db)
    return service.get_users(skip, limit)


@router.get('/count', response_model=UserCountResponse)
def count_users(db: Session = Depends(get_db_replica)):
    """Сколько читателей в библиотеке. После шардирования — сумма COUNT по шардам."""
    if sharding_enabled():
        return UserCountResponse(count=sharded_users.count_users())
    service = UserService(db)
    return UserCountResponse(count=service.count_users())


@router.get('/{user_id}', response_model=UserResponse)
def get_user(user_id: int, db: Session = Depends(get_db_for_user)):
    service = UserService(db)
    user = service.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail='User not found')
    return user


@router.post('/', response_model=UserResponse, status_code=201)
def create_user(user: UserCreate, db: Session = Depends(get_db)):
    if sharding_enabled():
        return sharded_users.create_user(user.name, user.email)
    service = UserService(db)
    return service.create_user(user.name, user.email)


@router.put('/{user_id}', response_model=UserResponse)
def update_user(
    user_id: int,
    user: UserUpdate,
    db: Session = Depends(get_db_for_user),
):
    service = UserService(db)
    updated = service.update_user(user_id, user.name, user.email)
    if not updated:
        raise HTTPException(status_code=404, detail='User not found')
    return updated


@router.delete('/{user_id}', status_code=204)
def delete_user(user_id: int, db: Session = Depends(get_db_for_user)):
    service = UserService(db)
    if not service.delete_user(user_id):
        raise HTTPException(status_code=404, detail='User not found')
    return None


@router.get('/{user_id}/bookings', response_model=list[BookingWithBookResponse])
def get_user_bookings(user_id: int, db: Session = Depends(get_db)):
    service = BookingService(db)
    return service.get_bookings_by_user_id(user_id)


@router.get('/{user_id}/reviews', response_model=list[ReviewWithBookResponse])
def get_user_reviews(
    user_id: int,
    skip: int = 0,
    limit: int = 20,
    db: Session = Depends(get_db),
):
    service = ReviewService(db)
    return service.get_reviews_by_user_id(user_id, skip, limit)
