"""Execution leases and ordered, detached thread persistence."""

import asyncio
import logging
from copy import deepcopy
from dataclasses import dataclass, field

from sqlalchemy.engine import Connection

from app.core.database import SessionLocal

from .repository import ThreadStateRepository

logger = logging.getLogger(__name__)


class ThreadBusy(ValueError):
    """An analysis or deletion already owns this conversation."""


@dataclass
class ThreadLease:
    thread_id: str
    connection: Connection
    active: bool = True
    pending: asyncio.Task | None = None
    finished: asyncio.Event = field(default_factory=asyncio.Event)
    releasing: asyncio.Task | None = None
    producer: asyncio.Task | None = None
    tool_tasks: set[asyncio.Task] = field(default_factory=set)
    finalizing: asyncio.Task | None = None


class ThreadStateService:
    def __init__(self, repository: ThreadStateRepository | None = None):
        self._repository = repository or ThreadStateRepository(SessionLocal)
        self.cache: dict[str, dict | None] = {}
        self._leases: dict[str, ThreadLease] = {}
        self._claims: dict[str, asyncio.Task] = {}
        self._claim_cleanup: set[asyncio.Task] = set()

    async def claim(self, thread_id: str) -> ThreadLease:
        if thread_id in self._leases or thread_id in self._claims:
            raise ThreadBusy("Analysis already running for this conversation")
        acquisition = asyncio.create_task(
            asyncio.to_thread(self._repository.acquire, thread_id)
        )
        self._claims[thread_id] = acquisition

        async def abandon():
            try:
                connection = await asyncio.shield(acquisition)
                if connection is not None:
                    await asyncio.to_thread(
                        self._repository.release, connection, thread_id
                    )
            except Exception:
                logger.exception(
                    "Failed to clean up cancelled conversation acquisition"
                )
            finally:
                self._claims.pop(thread_id, None)

        try:
            connection = await asyncio.shield(acquisition)
        except asyncio.CancelledError:
            cleanup = asyncio.create_task(abandon())
            self._claim_cleanup.add(cleanup)
            cleanup.add_done_callback(self._claim_cleanup.discard)
            raise
        except BaseException:
            self._claims.pop(thread_id, None)
            raise
        self._claims.pop(thread_id, None)
        if connection is None:
            raise ThreadBusy("Analysis already running for this conversation")
        lease = ThreadLease(thread_id, connection)
        self._leases[thread_id] = lease
        return lease

    async def release(self, lease: ThreadLease) -> None:
        if not lease.active:
            return

        async def finish():
            try:
                if lease.pending is not None:
                    await asyncio.shield(lease.pending)
            finally:
                lease.active = False
                self._leases.pop(lease.thread_id, None)
                try:
                    await asyncio.to_thread(
                        self._repository.release, lease.connection, lease.thread_id
                    )
                finally:
                    lease.producer = None
                    lease.finished.set()

        if lease.releasing is None:
            lease.releasing = asyncio.create_task(finish())
        # If the caller disconnects/cancels, finalization still owns the lock.
        await asyncio.shield(lease.releasing)

    async def load(self, thread_id: str) -> dict | None:
        # Other server processes can write while this process has an old cache.
        self.cache[thread_id] = await asyncio.to_thread(
            self._repository.load, thread_id
        )
        return deepcopy(self.cache[thread_id])

    def save(self, lease: ThreadLease, state: dict) -> asyncio.Future:
        snapshot = deepcopy(state)
        previous = lease.pending

        async def write():
            if previous is not None:
                await asyncio.shield(previous)
            if not lease.active:
                return
            await asyncio.to_thread(self._repository.save, lease.thread_id, snapshot)
            self.cache[lease.thread_id] = deepcopy(snapshot)

        task = asyncio.create_task(write())
        if lease.active:
            lease.pending = task
        # The caller may cancel this waiter; ordered SQL work remains owned by
        # the lease until release drains its actual task.
        return asyncio.shield(task)

    async def delete(self, thread_id: str, *, lease: ThreadLease | None = None) -> None:
        owns_lease = lease is None
        lease = lease or await self.claim(thread_id)
        if not lease.active or lease.thread_id != thread_id:
            raise ThreadBusy("Deletion requires an active execution lease")
        previous = lease.pending

        async def remove():
            if previous is not None:
                await asyncio.shield(previous)
            await asyncio.to_thread(self._repository.delete, thread_id)
            self.cache.pop(thread_id, None)

        async def release_after_cancel():
            try:
                await self.release(lease)
            except Exception:
                logger.exception("Failed to release cancelled conversation deletion")

        lease.pending = asyncio.create_task(remove())
        cancelled = False
        try:
            await asyncio.shield(lease.pending)
        except asyncio.CancelledError:
            cancelled = True
            if owns_lease:
                asyncio.create_task(release_after_cancel())
            raise
        finally:
            if owns_lease and not cancelled:
                await self.release(lease)


_thread_state_service = ThreadStateService()


def get_thread_state_service() -> ThreadStateService:
    return _thread_state_service
