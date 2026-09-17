#!/bin/sh
set -e

echo "Running database migrations..."
alembic upgrade head

echo "Initializing shard schemas..."
python -c "from app.sharding.schema import init_all_shards; print('shards', init_all_shards())"

echo "Starting application..."
exec "$@"
