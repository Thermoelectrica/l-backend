-- name: get_all_entity_property(modified_since)
-- Get all entity properties
-- :modified_since defaults to 1790-01-01 - only return rows modified after that timestamp
SELECT entity_id, entity_type, inspection_schedule_id, server_modified_at
FROM lesiv.entity_property
WHERE server_modified_at > :modified_since
ORDER BY server_modified_at;

-- name: get_by_plant_id(plant_id, modified_since)
-- Get all entity properties belonging to a plant: the plant's own row, its facilities, and the
-- equipment inside those facilities.
-- :modified_since defaults to 1790-01-01 - only return rows modified after that timestamp
SELECT ep.entity_id, ep.entity_type, ep.inspection_schedule_id, ep.server_modified_at
FROM lesiv.entity_property ep
WHERE ep.server_modified_at > :modified_since
  AND (
      (ep.entity_type = 'plant' AND ep.entity_id = :plant_id)
      OR (ep.entity_type = 'facility' AND ep.entity_id IN
          (SELECT f.id FROM lesiv.facility f WHERE f.plant_id = :plant_id))
      OR (ep.entity_type = 'equipment' AND ep.entity_id IN
          (SELECT e.id
           FROM lesiv.equipment e
           JOIN lesiv.facility f ON e.facility_id = f.id
           WHERE f.plant_id = :plant_id))
  )
ORDER BY ep.server_modified_at;

-- name: get_by_id(id)^
-- Get entity property by entity ID.
-- The parameter is named :id rather than :entity_id on purpose: every aggregate's get_by_id
-- collapses into one signature in the shared aiosql stub (see AGENTS.md 16.4), so it must take
-- exactly one parameter named id.
SELECT entity_id, entity_type, inspection_schedule_id, server_modified_at
FROM lesiv.entity_property
WHERE entity_id = :id;

-- name: upsert_entity_property(entity_id, entity_type, inspection_schedule_id, server_modified_at)!
-- Insert or update entity property
INSERT INTO lesiv.entity_property (entity_id, entity_type, inspection_schedule_id, server_modified_at)
VALUES (:entity_id, :entity_type, :inspection_schedule_id, :server_modified_at)
ON CONFLICT (entity_id) DO UPDATE SET
    entity_type = EXCLUDED.entity_type,
    inspection_schedule_id = EXCLUDED.inspection_schedule_id,
    server_modified_at = EXCLUDED.server_modified_at;
