"""EntityProperty router - entity attributes editable without a plant claim

Modifying equipment through PUT /equipment requires the caller's device to hold the pessimistic
claim on the whole plant. That is deliberately coarse for structural edits, but far too coarse for
a single attribute like the inspection schedule: one user scheduling one piece of equipment would
lock everyone else out of the entire plant until the claim goes stale.

So these attributes are their own aggregate and this router performs no claim check - the same
reasoning that split defects out of the equipment aggregate (see app/routers/defect.py). The
aggregate is polymorphic: entity_type says whether entity_id is a plant, a facility or a piece of
equipment. Callers still need plant access and INSPECT level to write.
"""

import logging
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from app.constants import DEFAULT_MODIFIED_SINCE
from app.database import get_db_connection
from app.dependencies.permissions import get_permission_service
from app.exceptions import ConcurrentModificationError
from app.models.entity_property import (
    EntityProperty,
    EntityPropertyListResponse,
    EntityType,
)
from app.models.inspector import AccessLevel
from app.repositories.entity_property import EntityPropertyRepository
from app.services.permission_service import PermissionService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/entity-property", tags=["entity-property"])
entity_property_repo = EntityPropertyRepository()


@router.get("/all", response_model=EntityPropertyListResponse)
async def get_all_entity_property(
    modified_since: datetime = Query(
        DEFAULT_MODIFIED_SINCE,
        description="Only return entity properties modified after this timestamp",
    ),
    conn=Depends(get_db_connection),
    permission_service: PermissionService = Depends(get_permission_service),
):
    """Get all entity properties, filtered by modification date and accessible plants"""
    all_properties = await entity_property_repo.get_all(conn, modified_since=modified_since)

    # Filter to only properties from accessible plants. Each row carries its own entity_type,
    # which is how the plant gets resolved: directly for plants, through the facility or
    # equipment otherwise.
    accessible_properties = []
    for properties in all_properties.items:
        plant_id = await permission_service.get_plant_id_from_entity(properties.entity_type, properties.entity_id)
        if plant_id and await permission_service.check_plant_access(plant_id):
            accessible_properties.append(properties)

    return EntityPropertyListResponse(items=accessible_properties)


@router.get("/by_id/{entity_id}", response_model=EntityProperty)
async def get_entity_property_by_id(
    entity_id: UUID,
    entity_type: EntityType = Query(
        ...,
        description="Kind of entity the id belongs to: plant, facility or equipment",
    ),
    conn=Depends(get_db_connection),
    permission_service: PermissionService = Depends(get_permission_service),
):
    """Get properties of a single entity.

    Returns an all-default object for an entity that has no properties row yet, so the client never
    has to distinguish "not scheduled" from "never written". A 404 means the *entity* is unknown.

    entity_type is a required query parameter because the id cannot be resolved to a plant without
    knowing which aggregate it belongs to.
    """
    plant_id = await permission_service.get_plant_id_from_entity(entity_type, entity_id)
    if not plant_id:
        raise HTTPException(status_code=404, detail="Entity not found")
    await permission_service.require_plant_access(plant_id)

    properties = await entity_property_repo.get_by_id(conn, entity_id)
    if not properties:
        return EntityProperty(entity_id=entity_id, entity_type=entity_type)
    return properties


@router.get("/by_plant_id/{plant_id}", response_model=list[EntityProperty])
async def get_entity_property_by_plant_id(
    plant_id: UUID,
    modified_since: datetime = Query(
        DEFAULT_MODIFIED_SINCE,
        description="Only return entity properties modified after this timestamp",
    ),
    conn=Depends(get_db_connection),
    permission_service: PermissionService = Depends(get_permission_service),
):
    """Get properties of the plant itself, its facilities and its equipment, optionally filtered
    by modification date.

    Entities without a properties row are omitted - there is nothing to sync for them.
    """
    # Check plant access
    await permission_service.require_plant_access(plant_id)

    return await entity_property_repo.get_by_plant_id(conn, plant_id, modified_since=modified_since)


@router.put("", response_model=EntityProperty)
async def upsert_entity_property(
    properties: EntityProperty,
    force: bool = Query(
        default=False,
        description="If true, ignore server_modified_at validation",
    ),
    conn=Depends(get_db_connection),
    permission_service: PermissionService = Depends(get_permission_service),
):
    """
    Create or replace the properties of one entity.

    Rules:
    - force=false (default):
      - Validates server_modified_at for existing properties
      - Ignores server_modified_at when the entity has no properties row yet
    - force=true:
      - Ignores server_modified_at validation

    Note: entity properties are NOT owned by plant claims - that is the whole point of this
    aggregate. The plant does not have to be claimed, and a claim held by another device does not
    block the write. Callers still need INSPECT level and access to the plant.
    """
    try:
        async with conn.transaction():
            # Check access level (INSPECT required)
            permission_service.require_access_level(AccessLevel.INSPECT)

            # Check plant access via the entity. A missing plant_id means the entity has not been
            # synced yet, which is allowed: the mobile client may push properties first.
            plant_id = await permission_service.get_plant_id_from_entity(properties.entity_type, properties.entity_id)
            if plant_id:
                await permission_service.require_plant_access(plant_id)

            result = await entity_property_repo.save(conn, properties, force=force)
        return result
    except ConcurrentModificationError as e:
        logger.warning(
            "Concurrent modification detected for entity property",
            extra={
                "entity_id": str(properties.entity_id),
                "conflict": e.conflict_error.model_dump(mode="json"),
            },
        )
        raise HTTPException(status_code=409, detail=e.conflict_error.model_dump(mode="json"))
    except ValueError as e:
        logger.warning(
            "Invalid entity property data",
            extra={"entity_id": str(properties.entity_id), "error": str(e)},
        )
        raise HTTPException(status_code=400, detail=str(e))
