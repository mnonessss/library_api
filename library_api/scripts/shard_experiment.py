#!/usr/bin/env python3
"""Лаба 5: распределение users по шардам и перенос при 3 → 4."""
import argparse
import os
import sys
from collections import Counter
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / '.env')

from sqlalchemy import text

from app.sharding.hashing import stable_hash
from app.sharding.pool import (
    iter_shard_sessions,
    shard_session_factories,
    shard_urls,
)
from app.sharding.router import ConsistentHashRing, ModuloRouter
from app.sharding.schema import init_all_shards


def pct(part: int, total: int) -> float:
    return 0.0 if total == 0 else 100.0 * part / total


def count_by(assign, keys) -> dict[int | str, int]:
    counter: Counter = Counter(assign(key) for key in keys)
    return dict(sorted(counter.items(), key=lambda item: str(item[0])))


def moved_count(old_assign, new_assign, keys) -> int:
    return sum(1 for key in keys if old_assign(key) != new_assign(key))


def bulk_insert_users(session, user_ids: list[int], batch: int = 2000) -> None:
    for start in range(0, len(user_ids), batch):
        chunk = user_ids[start:start + batch]
        session.execute(
            text(
                'INSERT INTO users (id, name, email) '
                'VALUES (:id, :name, :email)'
            ),
            [
                {
                    'id': user_id,
                    'name': f'User {user_id}',
                    'email': f'user{user_id}@library.local',
                }
                for user_id in chunk
            ],
        )
    session.commit()


def load_modulo(keys: list[int], n: int) -> dict[int, int]:
    router = ModuloRouter(n)
    buckets: dict[int, list[int]] = {i: [] for i in range(n)}
    for key in keys:
        buckets[router.shard_for(key)].append(key)

    factories = shard_session_factories()
    if len(factories) < n:
        raise RuntimeError(
            f'Need {n} shard URLs, got {len(factories)}: {shard_urls()}'
        )

    for index, user_ids in buckets.items():
        session = factories[index]()
        try:
            session.execute(text('TRUNCATE reviews, bookings, users'))
            session.commit()
            bulk_insert_users(session, user_ids)
            print(f'  inserted {len(user_ids)} users → shard-{index}')
        finally:
            session.close()
    return {index: len(ids) for index, ids in buckets.items()}


def db_counts() -> list[tuple[int, int]]:
    rows = []
    for index, session in enumerate(iter_shard_sessions()):
        try:
            count = session.execute(text('SELECT COUNT(*) FROM users')).scalar()
            rows.append((index, int(count or 0)))
        finally:
            session.close()
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--users', type=int, default=100_000)
    parser.add_argument('--vnodes', type=int, default=128)
    parser.add_argument('--skip-insert', action='store_true')
    args = parser.parse_args()

    keys = list(range(1, args.users + 1))
    print(f'SHARD_URLS={shard_urls()}')
    print(f'users={args.users}  vnodes={args.vnodes}')
    print()

    print('=== примеры hash(key) % 3 ===')
    modulo3 = ModuloRouter(3)
    for demo_key in (101, 102, 103, 1, 2, 3):
        digest = stable_hash(demo_key)
        print(
            f'  hash({demo_key}) = {digest}  '
            f'% 3 → shard {modulo3.shard_for(demo_key)}'
        )
    print()

    if not args.skip_insert:
        print('=== init schema + INSERT hash(key) % 3 ===')
        init_all_shards()
        load_modulo(keys, n=3)

    print()
    print('=== COUNT(*) на живых PostgreSQL ===')
    live = db_counts()
    for index, count in live:
        print(f'  Shard {index} → {count} записей')
    total = sum(count for _, count in live)
    print(f'  Всего: {total}')
    if total:
        counts_only = [count for _, count in live]
        delta = max(counts_only) - min(counts_only)
        print(
            f'  max-min = {delta}  '
            f'({pct(delta, total):.2f}% от всего)'
        )
    print()

    print('=== 3 shards → 4 shards, hash(key) % N ===')
    modulo4 = ModuloRouter(4)
    modulo_moved = moved_count(modulo3.shard_for, modulo4.shard_for, keys)
    modulo_stayed = args.users - modulo_moved
    print(f'  Всего записей: {args.users}')
    print(f'  Изменили shard: {modulo_moved}')
    print(f'  Не изменили: {modulo_stayed}')
    print(f'  Перемещено: {pct(modulo_moved, args.users):.2f}%')
    print()

    nodes3 = ['shard-0', 'shard-1', 'shard-2']
    nodes4 = ['shard-0', 'shard-1', 'shard-2', 'shard-3']

    print('=== Consistent Hashing, базовая версия (1 vnode) ===')
    ring3_basic = ConsistentHashRing(nodes3, virtual_nodes=1)
    ring4_basic = ConsistentHashRing(nodes4, virtual_nodes=1)
    basic_dist = count_by(ring3_basic.get_node, keys)
    basic_moved = moved_count(ring3_basic.get_node, ring4_basic.get_node, keys)
    for node, count in basic_dist.items():
        print(f'  {node} → {count}')
    print(
        f'  3→4 перемещено: {basic_moved} '
        f'({pct(basic_moved, args.users):.2f}%)'
    )
    print()

    print(f'=== Consistent Hashing + {args.vnodes} virtual nodes ===')
    ring3 = ConsistentHashRing(nodes3, virtual_nodes=args.vnodes)
    ring4 = ConsistentHashRing(nodes4, virtual_nodes=args.vnodes)
    ch_dist = count_by(ring3.get_node, keys)
    ch_moved = moved_count(ring3.get_node, ring4.get_node, keys)
    for node, count in ch_dist.items():
        print(f'  {node} → {count}')
    print(
        f'  3→4 перемещено: {ch_moved} '
        f'({pct(ch_moved, args.users):.2f}%)'
    )
    print()

    print('=== сравнение 3 → 4 ===')
    print(f'  {"стратегия":<32} {"перемещено"}')
    print(f'  {"hash(key) % N":<32} {pct(modulo_moved, args.users):.2f}%')
    print(
        f'  {"Consistent Hashing (1 vnode)":<32} '
        f'{pct(basic_moved, args.users):.2f}%'
    )
    print(
        f'  {f"Consistent Hashing ({args.vnodes} vnodes)":<32} '
        f'{pct(ch_moved, args.users):.2f}%'
    )

    print()
    print('=== 4 → 5 и удаление shard (CH + vnodes) ===')
    ring5 = ConsistentHashRing(
        ['shard-0', 'shard-1', 'shard-2', 'shard-3', 'shard-4'],
        virtual_nodes=args.vnodes,
    )
    ring_drop = ConsistentHashRing(
        ['shard-0', 'shard-1'],
        virtual_nodes=args.vnodes,
    )
    add5 = moved_count(ring4.get_node, ring5.get_node, keys)
    drop1 = moved_count(ring3.get_node, ring_drop.get_node, keys)
    print(
        f'  4→5 добавить shard: {add5} ({pct(add5, args.users):.2f}%)'
    )
    print(
        f'  3→2 удалить shard-2: {drop1} ({pct(drop1, args.users):.2f}%)'
    )


if __name__ == '__main__':
    if not os.environ.get('SHARD_DATABASE_URLS'):
        os.environ['SHARD_DATABASE_URLS'] = (
            'postgresql://{user}:{password}@postgres-shard-0:5432/{db},'
            'postgresql://{user}:{password}@postgres-shard-1:5432/{db},'
            'postgresql://{user}:{password}@postgres-shard-2:5432/{db}'
        ).format(
            user=os.environ.get('DB_USER', 'postgres'),
            password=os.environ.get('DB_PASSWORD', 'postgres'),
            db=os.environ.get('DB_NAME', 'library_db'),
        )
        import importlib
        import app.config as config_mod
        import app.sharding.pool as pool_mod
        importlib.reload(config_mod)
        pool_mod.shard_engines.cache_clear()
        pool_mod.shard_session_factories.cache_clear()
    main()
