from app.sharding.pool import get_router, sharding_enabled
from app.sharding.users import lookup, shard_counts

from fastapi import APIRouter, HTTPException


router = APIRouter(prefix='/api/admin/shards', tags=['admin-shards'])


@router.get('/')
def list_shards():
    if not sharding_enabled():
        raise HTTPException(status_code=404, detail='Sharding is not enabled')
    router_info = get_router()
    return {
        'strategy': router_info.strategy,
        'n': router_info.n,
        'virtual_nodes': router_info.ring.virtual_nodes,
        'shards': shard_counts(),
    }


@router.get('/lookup/{user_id}')
def lookup_user_shard(user_id: int):
    if not sharding_enabled():
        raise HTTPException(status_code=404, detail='Sharding is not enabled')
    return lookup(user_id)
