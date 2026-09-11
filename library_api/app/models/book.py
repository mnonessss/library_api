from app.database import Base

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Table
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func


# Связующая таблица для связи Many-to-Many между Book и Category
book_categories = Table(
    'book_categories',
    Base.metadata,
    Column('book_id', Integer, ForeignKey('books.id'), primary_key=True),
    Column('category_id', Integer, ForeignKey('categories.id'),
           primary_key=True)
)


class Book(Base):
    __tablename__ = 'books'

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False, index=True)
    author = Column(String, nullable=False)
    total_copies = Column(Integer, default=1)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Связь Many-to-Many.
    categories = relationship('Category', secondary=book_categories,
                              backref='books')
