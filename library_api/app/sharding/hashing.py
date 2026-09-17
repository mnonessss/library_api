import hashlib


def stable_hash(key) -> int:
    """Детерминированный hash: Python hash() нельзя — он солёный на процесс."""
    return int(hashlib.md5(str(key).encode('utf-8')).hexdigest(), 16)
