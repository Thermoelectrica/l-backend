-- name: get_all_equipment_properties(modified_since)
-- Get all equipment properties
-- :modified_since defaults to 1790-01-01 - only return rows modified after that timestamp
SELECT equipment_id, next_inspection_date, server_modified_at
FROM lesiv.equipment_properties
WHERE server_modified_at > :modified_since
ORDER BY server_modified_at;

-- name: get_by_plant_id(plant_id, modified_since)
-- Get all equipment properties for a plant - joins through equipment and facility
-- :modified_since defaults to 1790-01-01 - only return rows modified after that timestamp
SELECT ep.equipment_id, ep.next_inspection_date, ep.server_modified_at
FROM lesiv.equipment_properties ep
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
SELECT equipment_id, next_inspection_date, server_modified_at
FROM lesiv.equipment_properties
WHERE equipment_id = :id;

-- name: upsert_equipment_properties(equipment_id, next_inspection_date, server_modified_at)!
-- Insert or update equipment properties
INSERT INTO lesiv.equipment_properties (equipment_id, next_inspection_date, server_modified_at)
VALUES (:equipment_id, :next_inspection_date, :server_modified_at)
ON CONFLICT (equipment_id) DO UPDATE SET
    next_inspection_date = EXCLUDED.next_inspection_date,
    server_modified_at = EXCLUDED.server_modified_at;
