import bisect

from app.sharding.hashing import stable_hash


class ModuloRouter:
    """shard = hash(key) % N."""

    def __init__(self, n: int):
        if n <= 0:
            raise ValueError('n must be positive')
        self.n = n

    def shard_for(self, key) -> int:
        return stable_hash(key) % self.n


class ConsistentHashRing:
    """Hash ring: ключ → точка на кольце → ближайший shard по часовой.

    virtual_nodes=1 — базовая версия (одна точка на физический shard).
    Больше vnode сглаживает дуги и нагрузку.
    """

    def __init__(self, nodes: list[str], virtual_nodes: int = 1):
        if not nodes:
            raise ValueError('nodes must not be empty')
        if virtual_nodes < 1:
            raise ValueError('virtual_nodes must be >= 1')
        self.nodes = list(nodes)
        self.virtual_nodes = virtual_nodes
        points: list[tuple[int, str]] = []
        for node in self.nodes:
            for vnode in range(virtual_nodes):
                points.append((stable_hash(f'{node}#{vnode}'), node))
        points.sort(key=lambda item: item[0])
        self._hashes = [item[0] for item in points]
        self._owners = [item[1] for item in points]

    def get_node(self, key) -> str:
        digest = stable_hash(key)
        index = bisect.bisect_left(self._hashes, digest)
        if index == len(self._hashes):
            index = 0
        return self._owners[index]


class ShardRouter:
    """Единая точка выбора shard для backend."""

    def __init__(
        self,
        n: int,
        strategy: str = 'modulo',
        virtual_nodes: int = 128,
        names: list[str] | None = None,
    ):
        self.n = n
        self.strategy = strategy
        self.names = names or [f'shard-{i}' for i in range(n)]
        if len(self.names) != n:
            raise ValueError('names length must equal n')
        self.modulo = ModuloRouter(n)
        self.ring = ConsistentHashRing(self.names, virtual_nodes)

    def shard_index(self, key) -> int:
        if self.strategy == 'consistent':
            return self.names.index(self.ring.get_node(key))
        return self.modulo.shard_for(key)

    def shard_name(self, key) -> str:
        return self.names[self.shard_index(key)]
