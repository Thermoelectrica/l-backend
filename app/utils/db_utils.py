"""Utility functions for database operations"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Generic, List, Optional, Set, TypeVar

from app.exceptions import ConcurrentModificationError
from app.models import ConflictDetail, ConflictError
from app.utils.datetime_utils import truncate_to_milliseconds

T = TypeVar("T")


@dataclass
class CollectionConfig(Generic[T]):
    """Configuration for nested collection validation"""

    server_collection: List[T]
    client_collection: List[T]
    collection_name: str = "items"
    id_getter: Callable[[T], Any] = lambda x: getattr(x, "id", None)
    is_deleted_checker: Callable[[T], bool] = lambda x: getattr(x, "is_deleted", False)


class OptimisticLockingValidator:
    """Universal validator for optimistic locking"""

    @staticmethod
    def validate_timestamps(
        server_modified_at: datetime,
        client_modified_at: datetime,
        object_name: str = "object",
    ) -> None:
        """Validate timestamps"""
        if truncate_to_milliseconds(client_modified_at) != truncate_to_milliseconds(server_modified_at):
            raise ConcurrentModificationError(
                ConflictError(
                    message=f"{object_name} was modified by another client",
                    server_modified_at=server_modified_at,
                    client_modified_at=client_modified_at,
                    conflicts=[
                        ConflictDetail(
                            field="server_modified_at",
                            message="Timestamp mismatch",
                            server_value=server_modified_at.isoformat(),
                            client_value=client_modified_at.isoformat(),
                        )
                    ],
                )
            )

    @staticmethod
    def validate_extra_ids(server_ids: Set[Any], client_ids: Set[Any], collection_name: str = "items") -> None:
        """Validate that server doesn't have extra items"""
        extra_ids = server_ids - client_ids
        if extra_ids:
            raise ConcurrentModificationError(
                ConflictError(
                    message=f"Extra child {collection_name} exist on server",
                    server_modified_at=datetime.now(),  # Placeholder, should be actual server_modified_at
                    extra_child_ids=list(extra_ids),
                    conflicts=[
                        ConflictDetail(
                            field=collection_name,
                            message=f"Server has {len(extra_ids)} extra {collection_name} not in client request",
                        )
                    ],
                )
            )

    @classmethod
    def validate_collections(cls, configs: List[CollectionConfig]) -> None:
        """Validate multiple collections"""
        for config in configs:
            server_ids = {
                config.id_getter(item) for item in config.server_collection if not config.is_deleted_checker(item)
            }
            client_ids = {config.id_getter(item) for item in config.client_collection}
            cls.validate_extra_ids(server_ids, client_ids, config.collection_name)

    @classmethod
    def validate_object(
        cls,
        server_obj: Any,
        client_obj: Any,
        collection_configs: Optional[List[CollectionConfig]] = None,
    ) -> None:
        """Universal object validation"""
        if (
            hasattr(server_obj, "server_modified_at")
            and server_obj.server_modified_at is not None
            and hasattr(client_obj, "server_modified_at")
            and client_obj.server_modified_at is not None
        ):
            cls.validate_timestamps(
                server_modified_at=server_obj.server_modified_at,
                client_modified_at=client_obj.server_modified_at,
                object_name=server_obj.__class__.__name__,
            )

        if collection_configs:
            cls.validate_collections(collection_configs)
