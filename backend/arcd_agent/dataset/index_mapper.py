from __future__ import annotations

import json
from pathlib import Path


class IndexMapper:
    """Bidirectional mapping from raw string IDs to contiguous [0, N-1] indices.

    Supports arbitrary namespaces (e.g. "user", "question", "concept").

    Maps:
        phi_u : raw_user_id    -> {0, 1, ..., U-1}
        phi_q : raw_item_id    -> {0, 1, ..., Q-1}
        phi_s : raw_concept_id -> {0, 1, ..., S-1}
    """

    def __init__(self):
        self._maps: dict[str, dict[str, int]] = {}
        self._inv: dict[str, dict[int, str]] = {}

    def fit(self, namespace: str, raw_ids: list[str]) -> IndexMapper:
        unique = sorted(set(raw_ids))
        fwd = {raw: idx for idx, raw in enumerate(unique)}
        inv = {idx: raw for raw, idx in fwd.items()}
        self._maps[namespace] = fwd
        self._inv[namespace] = inv
        return self

    def encode(self, namespace: str, raw_id: str) -> int:
        return self._maps[namespace][raw_id]

    def decode(self, namespace: str, idx: int) -> str:
        return self._inv[namespace][idx]

    def encode_batch(self, namespace: str, raw_ids: list[str]) -> list[int]:
        m = self._maps[namespace]
        return [m[r] for r in raw_ids]

    def size(self, namespace: str) -> int:
        return len(self._maps[namespace])

    def contains(self, namespace: str, raw_id: str) -> bool:
        return raw_id in self._maps[namespace]

    def save(self, path: str | Path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(self._maps, f)

    @classmethod
    def load(cls, path: str | Path) -> IndexMapper:
        mapper = cls()
        with open(path) as f:
            mapper._maps = json.load(f)
        mapper._inv = {
            ns: {int(idx): raw for raw, idx in fwd.items()}
            for ns, fwd in mapper._maps.items()
        }
        return mapper

    def summary(self):
        for ns, m in self._maps.items():
            print(f"  {ns:>10s}: {len(m):>8,} unique IDs → [0, {len(m) - 1}]")
