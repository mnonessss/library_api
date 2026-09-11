import argparse
import os
import random
import sys
from datetime import datetime, timedelta

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from faker import Faker
from sqlalchemy import create_engine, func, text
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.models.user import User
from app.models.book import Book
from app.models.category import Category
from app.models.booking import Booking, BookingStatus
from app.models.review import Review

engine = create_engine(settings.DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)
fake = Faker()


def database_has_data(db) -> bool:
    count = db.execute(text('SELECT COUNT(*) FROM categories')).scalar()
    return count > 0


def reset_database(db):
    print('Очистка существующих данных...')
    db.execute(text(
        'TRUNCATE reviews, bookings, book_categories, books, '
        'categories, users RESTART IDENTITY CASCADE'
    ))
    db.commit()


def get_id_ranges(db):
    num_users = db.query(func.max(User.id)).scalar() or 0
    num_books = db.query(func.max(Book.id)).scalar() or 0
    return num_users, num_books


def generate_reviews(db, num_reviews: int, num_users: int, num_books: int):
    if num_users == 0 or num_books == 0:
        raise ValueError(
            'В базе нет пользователей или книг. '
            'Сначала выполните полную генерацию или используйте --reset.'
        )

    print(f'Массовая генерация {num_reviews} отзывов '
          f'(users: 1..{num_users}, books: 1..{num_books})...')
    reviews_to_insert = []
    base_review_date = datetime.now() - timedelta(days=180)

    for i in range(num_reviews):
        random_days = random.randint(0, 180)
        reviews_to_insert.append({
            'user_id': random.randint(1, num_users),
            'book_id': random.randint(1, num_books),
            'rating': random.randint(1, 5),
            'comment': fake.paragraph(nb_sentences=2),
            'created_at': base_review_date + timedelta(days=random_days),
        })

        if len(reviews_to_insert) >= 10000:
            db.execute(Review.__table__.insert(), reviews_to_insert)
            db.commit()
            reviews_to_insert = []
            print(f'Вставлено {i + 1} отзывов...')

    if reviews_to_insert:
        db.execute(Review.__table__.insert(), reviews_to_insert)
        db.commit()


def generate_full_data(db, num_users: int, num_books: int,
                       num_bookings: int, num_reviews: int):
    print('Генерация категорий...')
    categories = [Category(name=f'Category {i}') for i in range(10)]
    db.add_all(categories)
    db.commit()

    print(f'Генерация {num_users} пользователей...')
    users = [
        User(name=fake.name(), email=fake.unique.email())
        for _ in range(num_users)
    ]
    db.add_all(users)
    db.commit()

    print(f'Генерация {num_books} книг...')
    books = [
        Book(
            title=fake.sentence(nb_words=3),
            author=fake.name(),
            total_copies=random.randint(1, 10),
        )
        for _ in range(num_books)
    ]
    db.add_all(books)
    db.commit()

    for book in books:
        book.categories = random.sample(categories, k=random.randint(1, 3))
    db.commit()

    print(f'Массовая генерация {num_bookings} бронирований...')
    bookings_to_insert = []
    base_date = datetime.now() - timedelta(days=365)

    for i in range(num_bookings):
        random_days = random.randint(0, 365)
        created_at = base_date + timedelta(days=random_days)
        status = random.choice([
            BookingStatus.ACTIVE,
            BookingStatus.RETURNED,
            BookingStatus.OVERDUE,
        ])

        bookings_to_insert.append({
            'user_id': random.randint(1, num_users),
            'book_id': random.randint(1, num_books),
            'status': status,
            'created_at': created_at,
            'returned_at': (
                created_at + timedelta(days=random.randint(1, 14))
                if status != BookingStatus.ACTIVE else None
            ),
        })

        if len(bookings_to_insert) >= 10000:
            db.execute(Booking.__table__.insert(), bookings_to_insert)
            db.commit()
            bookings_to_insert = []
            print(f'Вставлено {i + 1} бронирований...')

    if bookings_to_insert:
        db.execute(Booking.__table__.insert(), bookings_to_insert)
        db.commit()

    generate_reviews(db, num_reviews, num_users, num_books)


def main():
    parser = argparse.ArgumentParser(
        description='Генерация тестовых данных для Library API'
    )
    parser.add_argument('--only-reviews', action='store_true',
                        help='Добавить только отзывы к существующим данным')
    parser.add_argument('--reset', action='store_true',
                        help='Очистить все таблицы и сгенерировать данные заново')
    parser.add_argument('--users', type=int, default=1000)
    parser.add_argument('--books', type=int, default=500)
    parser.add_argument('--bookings', type=int, default=100000)
    parser.add_argument('--reviews', type=int, default=50000)
    args = parser.parse_args()

    print(f'Подключение к базе данных: {settings.DATABASE_URL}')
    db = SessionLocal()

    try:
        if args.only_reviews:
            num_users, num_books = get_id_ranges(db)
            generate_reviews(db, args.reviews, num_users, num_books)
        else:
            if database_has_data():
                if not args.reset:
                    print(
                        '❌ В базе уже есть данные.\n'
                        '   Используйте --only-reviews для добавления отзывов\n'
                        '   или --reset для полной перегенерации.'
                    )
                    return
                reset_database(db)

            generate_full_data(
                db, args.users, args.books, args.bookings, args.reviews
            )

        print('✅ Генерация данных успешно завершена!')
    except Exception as e:
        print(f'❌ Ошибка при генерации данных: {e}')
        db.rollback()
    finally:
        db.close()


if __name__ == '__main__':
    main()
