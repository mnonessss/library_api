from app.api import bookings, books, reviews, users
from app.database import get_db

from fastapi import Depends, FastAPI, status
from fastapi.responses import JSONResponse

from sqlalchemy import text


app = FastAPI(
    title='Library Scaling API',
    description='Backend для сервиса библиотеки',
    version='1.0.0'
)

app.include_router(users.router)
app.include_router(books.router)
app.include_router(bookings.router)
app.include_router(reviews.router)


@app.get('/health')
def health_check(db=Depends(get_db)):
    try:
        db.execute(text('SELECT 1'))
        return {'status': 'healthy', 'database': 'connected'}
    except Exception as e:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={'status': 'unhealthy', 'error': str(e)},
        )
