"""Unit tests for OptimisticLockingValidator and CollectionConfig"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

import pytest

from app.exceptions import ConcurrentModificationError
from app.utils.db_utils import CollectionConfig, OptimisticLockingValidator

# ---------------------------------------------------------------------------
# Helpers / simple domain objects
# ---------------------------------------------------------------------------


@dataclass
class SimpleObj:
    """Minimal object with server_modified_at, used to test validate_object."""

    server_modified_at: Optional[datetime] = None


@dataclass
class ChildItem:
    """Minimal child entity with id and is_deleted."""

    id: object
    is_deleted: bool = False


def _dt(microsecond: int = 0) -> datetime:
    """Return a fixed UTC datetime with the given microsecond component."""
    return datetime(2024, 6, 1, 12, 0, 0, microsecond, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# validate_timestamps
# ---------------------------------------------------------------------------


class TestValidateTimestamps:
    def test_matching_timestamps_do_not_raise(self):
        """Identical timestamps must not raise."""
        ts = _dt(123_000)
        OptimisticLockingValidator.validate_timestamps(ts, ts)

    def test_timestamps_equal_at_millisecond_precision_do_not_raise(self):
        """Timestamps that differ only in sub-millisecond digits are considered equal."""
        server = _dt(123_456)  # 123.456 ms
        client = _dt(123_000)  # 123.000 ms — same millisecond after truncation
        OptimisticLockingValidator.validate_timestamps(server, client)

    def test_different_timestamps_raise(self):
        """Different timestamps (different milliseconds) must raise ConcurrentModificationError."""
        server = _dt(500_000)
        client = _dt(0)
        with pytest.raises(ConcurrentModificationError) as exc_info:
            OptimisticLockingValidator.validate_timestamps(server, client)
        err = exc_info.value.conflict_error
        assert err.type == "conflict"
        assert err.server_modified_at == server
        assert err.client_modified_at == client

    def test_error_contains_conflict_detail(self):
        """The raised error must include a ConflictDetail for server_modified_at."""
        server = _dt(1_000)
        client = _dt(2_000)
        with pytest.raises(ConcurrentModificationError) as exc_info:
            OptimisticLockingValidator.validate_timestamps(server, client)
        conflicts = exc_info.value.conflict_error.conflicts
        assert len(conflicts) == 1
        assert conflicts[0].field == "server_modified_at"

    def test_error_message_contains_object_name(self):
        """Custom object_name must appear in the error message."""
        server = _dt(1_000)
        client = _dt(2_000)
        with pytest.raises(ConcurrentModificationError) as exc_info:
            OptimisticLockingValidator.validate_timestamps(server, client, object_name="MyEntity")
        assert "MyEntity" in exc_info.value.conflict_error.message

    def test_default_object_name_used_when_not_provided(self):
        """Default object_name 'object' is used when not specified."""
        server = _dt(1_000)
        client = _dt(2_000)
        with pytest.raises(ConcurrentModificationError) as exc_info:
            OptimisticLockingValidator.validate_timestamps(server, client)
        assert "object" in exc_info.value.conflict_error.message

    def test_conflict_detail_contains_isoformat_values(self):
        """ConflictDetail server_value and client_value must be ISO-format strings."""
        server = _dt(1_000)
        client = _dt(2_000)
        with pytest.raises(ConcurrentModificationError) as exc_info:
            OptimisticLockingValidator.validate_timestamps(server, client)
        detail = exc_info.value.conflict_error.conflicts[0]
        assert detail.server_value == server.isoformat()
        assert detail.client_value == client.isoformat()


# ---------------------------------------------------------------------------
# validate_extra_ids
# ---------------------------------------------------------------------------


class TestValidateExtraIds:
    def test_no_extra_ids_does_not_raise(self):
        """When server_ids ⊆ client_ids there are no extras — must not raise."""
        server_ids = {uuid4(), uuid4()}
        client_ids = set(server_ids)
        OptimisticLockingValidator.validate_extra_ids(server_ids, client_ids)

    def test_client_has_more_ids_does_not_raise(self):
        """Client may have IDs the server doesn't know about (new items) — must not raise."""
        shared = uuid4()
        server_ids = {shared}
        client_ids = {shared, uuid4()}
        OptimisticLockingValidator.validate_extra_ids(server_ids, client_ids)

    def test_extra_server_ids_raise(self):
        """When server has IDs not present in client, ConcurrentModificationError is raised."""
        extra_id = uuid4()
        server_ids = {uuid4(), extra_id}
        client_ids = server_ids - {extra_id}
        with pytest.raises(ConcurrentModificationError) as exc_info:
            OptimisticLockingValidator.validate_extra_ids(server_ids, client_ids)
        err = exc_info.value.conflict_error
        assert extra_id in err.extra_child_ids

    def test_error_lists_all_extra_ids(self):
        """All extra IDs must appear in extra_child_ids."""
        extra_1, extra_2 = uuid4(), uuid4()
        server_ids = {uuid4(), extra_1, extra_2}
        client_ids = server_ids - {extra_1, extra_2}
        with pytest.raises(ConcurrentModificationError) as exc_info:
            OptimisticLockingValidator.validate_extra_ids(server_ids, client_ids)
        extra_child_ids = exc_info.value.conflict_error.extra_child_ids
        assert extra_1 in extra_child_ids
        assert extra_2 in extra_child_ids

    def test_error_message_contains_collection_name(self):
        """Custom collection_name must appear in the error message."""
        extra_id = uuid4()
        with pytest.raises(ConcurrentModificationError) as exc_info:
            OptimisticLockingValidator.validate_extra_ids({extra_id}, set(), collection_name="widgets")
        assert "widgets" in exc_info.value.conflict_error.message

    def test_default_collection_name_used_when_not_provided(self):
        """Default collection_name 'items' is used when not specified."""
        extra_id = uuid4()
        with pytest.raises(ConcurrentModificationError) as exc_info:
            OptimisticLockingValidator.validate_extra_ids({extra_id}, set())
        assert "items" in exc_info.value.conflict_error.message

    def test_empty_server_and_client_ids_do_not_raise(self):
        """Both empty sets — nothing to conflict."""
        OptimisticLockingValidator.validate_extra_ids(set(), set())

    def test_conflict_detail_describes_count(self):
        """ConflictDetail message must mention the number of extra items."""
        extra_1, extra_2 = uuid4(), uuid4()
        server_ids = {extra_1, extra_2}
        with pytest.raises(ConcurrentModificationError) as exc_info:
            OptimisticLockingValidator.validate_extra_ids(server_ids, set(), collection_name="steps")
        detail = exc_info.value.conflict_error.conflicts[0]
        assert "2" in detail.message
        assert "steps" in detail.message


# ---------------------------------------------------------------------------
# validate_collections
# ---------------------------------------------------------------------------


class TestValidateCollections:
    def _make_config(self, server_items, client_items, name="items"):
        return CollectionConfig(
            server_collection=server_items,
            client_collection=client_items,
            collection_name=name,
        )

    def test_matching_collections_do_not_raise(self):
        """Server and client have the same active IDs — no conflict."""
        ids = [uuid4(), uuid4()]
        server = [ChildItem(id=i) for i in ids]
        client = [ChildItem(id=i) for i in ids]
        config = self._make_config(server, client)
        OptimisticLockingValidator.validate_collections([config])

    def test_deleted_server_items_are_excluded_from_check(self):
        """Items marked is_deleted=True on the server are not counted as extras."""
        active_id = uuid4()
        deleted_id = uuid4()
        server = [ChildItem(id=active_id), ChildItem(id=deleted_id, is_deleted=True)]
        client = [ChildItem(id=active_id)]
        config = self._make_config(server, client)
        # deleted_id is on server but not in client — should NOT raise because it's deleted
        OptimisticLockingValidator.validate_collections([config])

    def test_extra_active_server_item_raises(self):
        """An active server item absent from client triggers a conflict."""
        extra_id = uuid4()
        server = [ChildItem(id=uuid4()), ChildItem(id=extra_id)]
        client = [ChildItem(id=server[0].id)]
        config = self._make_config(server, client, name="facilities")
        with pytest.raises(ConcurrentModificationError) as exc_info:
            OptimisticLockingValidator.validate_collections([config])
        assert extra_id in exc_info.value.conflict_error.extra_child_ids

    def test_multiple_configs_all_valid_do_not_raise(self):
        """Multiple valid configs — none should raise."""
        id_a, id_b = uuid4(), uuid4()
        config_a = self._make_config([ChildItem(id=id_a)], [ChildItem(id=id_a)], "steps")
        config_b = self._make_config([ChildItem(id=id_b)], [ChildItem(id=id_b)], "defects")
        OptimisticLockingValidator.validate_collections([config_a, config_b])

    def test_first_invalid_config_raises_immediately(self):
        """Validation stops at the first conflicting collection."""
        extra_id = uuid4()
        bad_config = self._make_config([ChildItem(id=extra_id)], [], "steps")
        good_config = self._make_config([], [], "defects")
        with pytest.raises(ConcurrentModificationError):
            OptimisticLockingValidator.validate_collections([bad_config, good_config])

    def test_empty_collections_do_not_raise(self):
        """Both server and client collections empty — no conflict."""
        config = self._make_config([], [])
        OptimisticLockingValidator.validate_collections([config])

    def test_custom_id_getter_is_used(self):
        """CollectionConfig.id_getter is respected when extracting IDs.

        ConflictError.extra_child_ids only accepts UUID | int values, so the
        custom id_getter must return a UUID (or int) for the error to be built.
        """

        @dataclass
        class WeirdItem:
            uid: object  # UUID stored under a non-standard attribute name
            is_deleted: bool = False

        extra_uid = uuid4()
        shared_uid = uuid4()
        server = [WeirdItem(uid=shared_uid), WeirdItem(uid=extra_uid)]
        client = [WeirdItem(uid=shared_uid)]
        config = CollectionConfig(
            server_collection=server,
            client_collection=client,
            collection_name="things",
            id_getter=lambda x: x.uid,
        )
        with pytest.raises(ConcurrentModificationError) as exc_info:
            OptimisticLockingValidator.validate_collections([config])
        assert extra_uid in exc_info.value.conflict_error.extra_child_ids

    def test_custom_is_deleted_checker_is_used(self):
        """CollectionConfig.is_deleted_checker is respected when filtering deleted items."""

        @dataclass
        class FlaggedItem:
            id: object
            removed: bool = False  # non-standard deletion flag

        extra_id = uuid4()
        server = [FlaggedItem(id=extra_id, removed=True)]
        client = []
        config = CollectionConfig(
            server_collection=server,
            client_collection=client,
            collection_name="things",
            is_deleted_checker=lambda x: x.removed,
        )
        # extra_id is "deleted" via custom checker — must NOT raise
        OptimisticLockingValidator.validate_collections([config])


# ---------------------------------------------------------------------------
# validate_object
# ---------------------------------------------------------------------------


class TestValidateObject:
    def test_matching_timestamps_do_not_raise(self):
        """Objects with matching server_modified_at must not raise."""
        ts = _dt(0)
        server = SimpleObj(server_modified_at=ts)
        client = SimpleObj(server_modified_at=ts)
        OptimisticLockingValidator.validate_object(server, client)

    def test_mismatched_timestamps_raise(self):
        """Objects with different server_modified_at must raise."""
        server = SimpleObj(server_modified_at=_dt(1_000))
        client = SimpleObj(server_modified_at=_dt(2_000))
        with pytest.raises(ConcurrentModificationError):
            OptimisticLockingValidator.validate_object(server, client)

    def test_none_server_modified_at_skips_timestamp_check(self):
        """If server_modified_at is None on the server object, timestamp check is skipped."""
        server = SimpleObj(server_modified_at=None)
        client = SimpleObj(server_modified_at=_dt(999_000))
        # Should not raise — no timestamp to compare
        OptimisticLockingValidator.validate_object(server, client)

    def test_none_client_modified_at_skips_timestamp_check(self):
        """If server_modified_at is None on the client object, timestamp check is skipped."""
        server = SimpleObj(server_modified_at=_dt(999_000))
        client = SimpleObj(server_modified_at=None)
        OptimisticLockingValidator.validate_object(server, client)

    def test_object_without_server_modified_at_attribute_skips_check(self):
        """Objects that lack server_modified_at entirely skip the timestamp check."""

        @dataclass
        class NoTimestamp:
            name: str

        OptimisticLockingValidator.validate_object(NoTimestamp("a"), NoTimestamp("b"))

    def test_collection_configs_validated_when_provided(self):
        """Extra child IDs in collection_configs trigger a conflict."""
        ts = _dt(0)
        server = SimpleObj(server_modified_at=ts)
        client = SimpleObj(server_modified_at=ts)

        extra_id = uuid4()
        config = CollectionConfig(
            server_collection=[ChildItem(id=extra_id)],
            client_collection=[],
            collection_name="steps",
        )
        with pytest.raises(ConcurrentModificationError) as exc_info:
            OptimisticLockingValidator.validate_object(server, client, collection_configs=[config])
        assert extra_id in exc_info.value.conflict_error.extra_child_ids

    def test_no_collection_configs_skips_collection_check(self):
        """When collection_configs is None, no collection check is performed."""
        ts = _dt(0)
        server = SimpleObj(server_modified_at=ts)
        client = SimpleObj(server_modified_at=ts)
        OptimisticLockingValidator.validate_object(server, client, collection_configs=None)

    def test_timestamp_checked_before_collections(self):
        """Timestamp mismatch is raised before collection conflicts are evaluated."""
        server = SimpleObj(server_modified_at=_dt(1_000))
        client = SimpleObj(server_modified_at=_dt(2_000))

        extra_id = uuid4()
        config = CollectionConfig(
            server_collection=[ChildItem(id=extra_id)],
            client_collection=[],
            collection_name="steps",
        )
        with pytest.raises(ConcurrentModificationError) as exc_info:
            OptimisticLockingValidator.validate_object(server, client, collection_configs=[config])
        # The error must be about the timestamp, not the extra child IDs
        err = exc_info.value.conflict_error
        assert err.server_modified_at == _dt(1_000)
        assert len(err.extra_child_ids) == 0

    def test_class_name_used_as_object_name_in_error(self):
        """The class name of server_obj is used as object_name in the timestamp error message."""

        @dataclass
        class MySpecialEntity:
            server_modified_at: Optional[datetime] = None

        server = MySpecialEntity(server_modified_at=_dt(1_000))
        client = MySpecialEntity(server_modified_at=_dt(2_000))
        with pytest.raises(ConcurrentModificationError) as exc_info:
            OptimisticLockingValidator.validate_object(server, client)
        assert "MySpecialEntity" in exc_info.value.conflict_error.message

    def test_valid_timestamps_and_valid_collections_do_not_raise(self):
        """Both timestamp and collections valid — no exception raised."""
        ts = _dt(0)
        server = SimpleObj(server_modified_at=ts)
        client = SimpleObj(server_modified_at=ts)
        shared_id = uuid4()
        config = CollectionConfig(
            server_collection=[ChildItem(id=shared_id)],
            client_collection=[ChildItem(id=shared_id)],
            collection_name="items",
        )
        OptimisticLockingValidator.validate_object(server, client, collection_configs=[config])
