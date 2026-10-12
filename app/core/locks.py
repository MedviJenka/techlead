"""Per-business write lock shared by every backend and worker process (MAIN_PLAN §65).

Lead writes match-then-save (deduplication), which spans several database requests, so two processes saving the
same business at once could both create a lead for one person. The lock is a lease row in ``business_locks``
(``try_lock_business`` in db/004_functions.sql), renewed while held; a crashed holder's lease simply expires.
"""

import asyncio
import os
import socket
import uuid
from collections import defaultdict
from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager, suppress
from typing import Protocol

from supabase import AsyncClient

from app.core.errors import ServiceUnavailableError
from app.core.logger import Logger

logger = Logger("locks")

PROCESS_ID = f"{socket.gethostname()}:{os.getpid()}"


class BusinessBusyError(ServiceUnavailableError):
    code = "business_busy"


class BusinessLock(Protocol):
    def hold(self, business_id: uuid.UUID) -> AbstractAsyncContextManager[None]: ...


class LocalBusinessLock:
    """One process only (tests and in-memory services). Waiters queue in arrival order."""

    def __init__(self) -> None:
        self._locks: defaultdict[uuid.UUID, asyncio.Lock] = defaultdict(asyncio.Lock)

    @asynccontextmanager
    async def hold(self, business_id: uuid.UUID) -> AsyncIterator[None]:
        async with self._locks[business_id]:
            yield


# Shared by every DatabaseBusinessLock of the process, so its own tasks queue here instead of polling the database.
_local = LocalBusinessLock()


class DatabaseBusinessLock:
    def __init__(
        self,
        db: AsyncClient,
        *,
        ttl_seconds: int = 30,
        poll_seconds: float = 0.2,
        wait_seconds: float = 30.0,
    ) -> None:
        self._db = db
        self._ttl = ttl_seconds
        self._poll = poll_seconds
        self._wait = wait_seconds

    @asynccontextmanager
    async def hold(self, business_id: uuid.UUID) -> AsyncIterator[None]:
        """Hold the business's lease for the block; ``BusinessBusyError`` when it stays taken for ``wait_seconds``."""
        async with _local.hold(business_id):
            holder = f"{PROCESS_ID}:{uuid.uuid4().hex[:12]}"
            await self._acquire(business_id, holder)
            renewal = asyncio.create_task(self._renew(business_id, holder))
            try:
                yield
            finally:
                renewal.cancel()
                with suppress(asyncio.CancelledError):
                    await renewal
                await self._release(business_id, holder)

    async def _try(self, business_id: uuid.UUID, holder: str) -> bool:
        params = {"p_business_id": str(business_id), "p_holder": holder, "p_ttl_seconds": self._ttl}
        response = await self._db.rpc("try_lock_business", params).execute()
        return response.data is True

    async def _acquire(self, business_id: uuid.UUID, holder: str) -> None:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self._wait
        while not await self._try(business_id, holder):
            if loop.time() >= deadline:
                logger.fire("business_lock_timeout", level="warning", business_id=str(business_id))
                raise BusinessBusyError("This business is busy with another change; try again shortly")
            await asyncio.sleep(self._poll)

    async def _renew(self, business_id: uuid.UUID, holder: str) -> None:
        while True:
            await asyncio.sleep(self._ttl / 3)
            try:
                renewed = await self._try(business_id, holder)
            except Exception as exc:
                logger.fire("business_lock_renew_failed", level="error", _exc_info=exc, business_id=str(business_id))
                continue
            if not renewed:
                logger.fire("business_lock_lost", level="error", business_id=str(business_id), holder=holder)

    async def _release(self, business_id: uuid.UUID, holder: str) -> None:
        """A failed release is logged only: the lease expires after ``ttl_seconds`` anyway."""
        try:
            await (
                self._db.table("business_locks")
                .delete()
                .eq("business_id", str(business_id))
                .eq("holder", holder)
                .execute()
            )
        except Exception as exc:
            logger.fire("business_lock_release_failed", level="error", _exc_info=exc, business_id=str(business_id))
