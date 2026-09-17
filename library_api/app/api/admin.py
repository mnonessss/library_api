from app.database import get_db
from app.jobs.create_partitions import run_create_partitions
from app.jobs.partition_health import run_partition_health
from app.partitioning import MANAGED_TARGETS, PartitionManager

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session


router = APIRouter(prefix='/admin/partitions', tags=['admin'])


@router.get('/')
def list_partitions(db: Session = Depends(get_db)):
    manager = PartitionManager(db)
    return [manager.health(target) for target in MANAGED_TARGETS]


@router.post('/create')
def create_partitions():
    return run_create_partitions()


@router.post('/health')
def check_health(force: bool = False):
    return run_partition_health(force=force)


@router.post('/demo/break')
def break_future_partition(db: Session = Depends(get_db)):
    """Drop farthest required partition of each managed table (events + bookings)."""
    manager = PartitionManager(db)
    dropped = []
    for target in MANAGED_TARGETS:
        required = manager.required_periods(target)
        name = manager.partition_name(target, required[-1])
        manager.drop_partition(target, name)
        dropped.append(f'{target.schema}.{name}')
    return {'dropped': dropped, 'health': run_partition_health()}


@router.post('/demo/restore')
def restore_partitions():
    created = run_create_partitions()
    health = run_partition_health()
    return {'created': created, 'health': health}
