-- name: get_all_equipment_property(modified_since)
-- Get all equipment properties
-- :modified_since defaults to 1790-01-01 - only return rows modified after that timestamp
SELECT equipment_id, inspection_schedule_id, server_modified_at
FROM lesiv.equipment_property
WHERE server_modified_at > :modified_since
ORDER BY server_modified_at;

-- name: get_by_plant_id(plant_id, modified_since)
-- Get all equipment properties for a plant - joins through equipment and facility
-- :modified_since defaults to 1790-01-01 - only return rows modified after that timestamp
SELECT ep.equipment_id, ep.inspection_schedule_id, ep.server_modified_at
FROM lesiv.equipment_property ep
JOIN lesiv.equipment e ON ep.equipment_id = e.id
JOIN lesiv.facility f ON e.facility_id = f.id
WHERE f.plant_id = :plant_id
  AND ep.server_modified_at > :modified_since
ORDER BY ep.server_modified_at;

-- name: get_by_id(id)^
-- Get equipment properties by equipment ID.
-- The parameter is named :id rather than :equipment_id on purpose: every aggregate's get_by_id
-- collapses into one signature in the shared aiosql stub (see AGENTS.md 16.4), so it must take
-- exactly one parameter named id.
SELECT equipment_id, inspection_schedule_id, server_modified_at
FROM lesiv.equipment_property
WHERE equipment_id = :id;

-- name: upsert_equipment_property(equipment_id, inspection_schedule_id, server_modified_at)!
-- Insert or update equipment properties
INSERT INTO lesiv.equipment_property (equipment_id, inspection_schedule_id, server_modified_at)
VALUES (:equipment_id, :inspection_schedule_id, :server_modified_at)
ON CONFLICT (equipment_id) DO UPDATE SET
    inspection_schedule_id = EXCLUDED.inspection_schedule_id,
    server_modified_at = EXCLUDED.server_modified_at;