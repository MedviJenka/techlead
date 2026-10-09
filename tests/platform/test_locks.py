"""The per-business lock (app/core/locks.py) on a fake ``business_locks`` lease: serialization, renewal, timeout."""

import asyncio
import uuid
from collections.abc import Callable
from types import SimpleNamespace
from typing import Any

import pytest

from app.core.locks import BusinessBusyError, DatabaseBusinessLock, LocalBusinessLock

BUSINESS = uuid.uuid4()


class _Query:
    def __init__(self, run: Callable[[dict[str, str]], Any]) -> None:
        self._run = run
        self._filters: dict[str, str] = {}

    def eq(self, column: str, value: str) -> "_Query":
        self._filters[column] = value
        return self

    async def execute(self) -> SimpleNamespace:
        return SimpleNamespace(data=self._run(self._filters))


class FakeLeaseDb:
    """``try_lock_business`` and the ``business_locks`` delete, without expiry (tests set ``holder`` directly)."""

    def __init__(self) -> None:
        self.holder: str | None = None
        self.calls: list[tuple[str, str]] = []

    def rpc(self, name: str, params: dict[str, Any]) -> _Query:
        def run(filters: dict[str, str]) -> bool | None:
            self.calls.append(("try", params["p_holder"]))
            if self.holder in (None, params["p_holder"]):
                self.holder = params["p_holder"]
                return True
            return None

        return _Query(run)

    def table(self, name: str) -> Any:
        def delete(filters: dict[str, str]) -> list[Any]:
            holder = filters["holder"]
            self.calls.append(("release", holder))
            if holder == self.holder and filters["business_id"] == str(BUSINESS):
                self.holder = None
            return []

        return SimpleNamespace(delete=lambda: _Query(delete))


async def test_local_lock_serializes_one_business_only() -> None:
    lock, order = LocalBusinessLock(), []

    async def hold(business: uuid.UUID, name: str) -> None:
        async with lock.hold(business):
            order.append(f"{name}+")
            await asyncio.sleep(0.01)
            order.append(f"{name}-")

    await asyncio.gather(hold(BUSINESS, "a"), hold(BUSINESS, "b"), hold(uuid.uuid4(), "c"))

    assert order.index("a-") < order.index("b+")
    assert order.index("c+") < order.index("a-")  # another business never waits


async def test_lease_is_taken_and_released() -> None:
    db = FakeLeaseDb()
    lock = DatabaseBusinessLock(db, ttl_seconds=30)  # type: ignore[arg-type]

    async with lock.hold(BUSINESS):
        holder = db.holder
        assert holder is not None

    assert db.holder is None and db.calls == [("try", holder), ("release", holder)]


async def test_waits_for_another_process_then_gives_up() -> None:
    db = FakeLeaseDb()
    db.holder = "other-process"
    lock = DatabaseBusinessLock(db, poll_seconds=0.01, wait_seconds=0.05)  # type: ignore[arg-type]

    with pytest.raises(BusinessBusyError):
        async with lock.hold(BUSINESS):
            pass

    assert len(db.calls) >= 3 and db.holder == "other-process"


async def test_waits_until_the_other_holder_releases() -> None:
    db = FakeLeaseDb()
    db.holder = "other-process"
    lock = DatabaseBusinessLock(db, poll_seconds=0.01, wait_seconds=1)  # type: ignore[arg-type]

    async def release_later() -> None:
        await asyncio.sleep(0.03)
        db.holder = None

    async def take() -> str | None:
        async with lock.hold(BUSINESS):
            return db.holder

    holder, _ = await asyncio.gather(take(), release_later())

    assert holder is not None and holder != "other-process"


async def test_lease_is_renewed_while_held() -> None:
    db = FakeLeaseDb()
    lock = DatabaseBusinessLock(db, ttl_seconds=0.03)  # type: ignore[arg-type]

    async with lock.hold(BUSINESS):
        await asyncio.sleep(0.05)

    assert [kind for kind, _ in db.calls].count("try") >= 3
