"""`InMemoryEventStore` against the shared `EventStore` contract (M6-Persistence
planning s16) - the same suite `PostgresEventStore` runs in
`tests/integration/test_event_store_postgres.py`."""

from __future__ import annotations

from uuid import uuid4

import pytest

from mindtrace.domain.ids import UserId
from mindtrace.events.in_memory_store import InMemoryEventStore
from mindtrace.events.store import EventStore
from tests.support.event_store_contract import EventStoreContractTests


class TestInMemoryEventStoreContract(EventStoreContractTests):
    @pytest.fixture
    def store(self) -> EventStore:
        return InMemoryEventStore()

    @pytest.fixture
    def user_a(self) -> UserId:
        return UserId(uuid4())

    @pytest.fixture
    def user_b(self) -> UserId:
        return UserId(uuid4())
