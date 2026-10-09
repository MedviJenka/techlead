"""Per-agent CrewAI memory, kept in a local LanceDB table and mirrored to object storage.

CrewAI's LanceDB storage only works on a local directory, so each agent's memory runs out of a
local cache: it is downloaded on first use in this process and new files are uploaded after
every crew run. LanceDB never rewrites a file (each write adds new data, manifest and index
files), so a sync only uploads files the bucket does not have yet.

Each memory belongs to one business, crew and agent; nothing is shared across businesses.

Limitation: run ONE backend replica. Two processes that write the same agent's memory each
add the same next version file and the last upload wins, and a process never re-downloads a
memory it already has, so it would not see the other's writes. Within one process the shared
local table is safe: LanceDB serialises writes through ``store_lock``.
"""

import re
import shutil
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from crewai import Memory
from crewai.llms.base_llm import BaseLLM
from crewai.memory.storage.lancedb_storage import LanceDBStorage
from crewai_core.lock_store import lock as store_lock

from ai.memory.object_store import ObjectStore
from app.core.logger import Logger

_SEGMENT = re.compile(r"^[A-Za-z0-9_-]+$")


logger = Logger(__name__)


@dataclass(frozen=True)
class MemoryKey:
    """Whose memory: one agent of one crew for one business."""

    business_id: str
    crew: str
    agent: str

    def __post_init__(self) -> None:
        for segment in (self.business_id, self.crew, self.agent):
            if not _SEGMENT.match(segment):
                raise ValueError(f"Memory key segment {segment!r} must match {_SEGMENT.pattern}")

    @property
    def prefix(self) -> str:
        return f"business/{self.business_id}/{self.crew}/{self.agent}/"


class AgentMemoryStore:
    def __init__(self, objects: ObjectStore, cache_dir: Path, embedder: Any = None) -> None:
        self._objects = objects
        self._cache_dir = cache_dir
        self._embedder = embedder
        self._lock = threading.Lock()
        self._key_locks: dict[MemoryKey, threading.Lock] = {}
        # Per key, the relative paths known to be in the bucket (downloaded or already uploaded).
        self._synced: dict[MemoryKey, set[str]] = {}

    def path(self, key: MemoryKey) -> Path:
        return self._cache_dir / key.prefix

    def memory(self, key: MemoryKey, llm: BaseLLM) -> Memory:
        """The agent's Memory, downloading it from the bucket the first time this process uses it.

        ``llm`` analyses what to remember (scope, categories, importance) on every save.
        """
        path = self._checkout(key)
        # No background compaction: it rewrites files while a sync may be uploading them.
        return Memory(llm=llm, storage=LanceDBStorage(path=path, compact_every=0), embedder=self._embedder)

    def sync(self, key: MemoryKey) -> int:
        """Upload the files this memory gained since the last sync. Returns how many were uploaded."""
        path = self.path(key)
        if not path.is_dir():
            return 0
        uploaded = 0
        with self._key_lock(key), store_lock(_lancedb_lock_name(path)):  # no LanceDB write mid-upload
            synced = self._synced.setdefault(key, set())
            for file in sorted(p for p in path.rglob("*") if p.is_file()):
                rel = file.relative_to(path).as_posix()
                if rel in synced:
                    continue
                self._objects.upload(file, key.prefix + rel)
                synced.add(rel)
                uploaded += 1
        if uploaded:
            logger.fire("agent_memory_synced", prefix=key.prefix, files=uploaded)
        return uploaded

    def reset(self, key: MemoryKey) -> None:
        """Forget everything this agent remembers for this business, in the bucket and locally."""
        with self._key_lock(key):
            self._objects.delete_prefix(key.prefix)
            shutil.rmtree(self.path(key), ignore_errors=True)
            self._synced.pop(key, None)

    def _checkout(self, key: MemoryKey) -> Path:
        path = self.path(key)
        with self._key_lock(key):
            if key in self._synced:
                return path
            synced: set[str] = set()
            for remote in self._objects.list_keys(key.prefix):
                rel = remote[len(key.prefix) :]
                if not rel:
                    continue
                if not (path / rel).exists():
                    self._objects.download(remote, path / rel)
                synced.add(rel)
            path.mkdir(parents=True, exist_ok=True)
            self._synced[key] = synced
            logger.fire("agent_memory_checked_out", prefix=key.prefix, files=len(synced))
            return path

    def _key_lock(self, key: MemoryKey) -> threading.Lock:
        with self._lock:
            return self._key_locks.setdefault(key, threading.Lock())


def _lancedb_lock_name(path: Path) -> str:
    """The lock LanceDBStorage holds around every write to this table (see its ``_lock_name``)."""
    return f"lancedb:{Path(path).resolve()}"
