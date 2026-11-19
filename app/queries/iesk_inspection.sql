-- IESK inspection aggregate queries (root lesiv.iesk_inspection + links lesiv.iesk_image)

-- name: get_all_iesk_inspections(modified_since)
-- Get all IESK inspections (lightweight list)
-- plant_id is returned so the router can filter by accessible plants in one pass
-- :modified_since defaults to 1790-01-01 - only return inspections modified after that timestamp
SELECT ii.id, ii.equipment_id, ii.inspector_id, ii.started_at, ii.completed_at, ii.status, ii.is_deleted,
       ii.server_modified_at, f.plant_id
FROM lesiv.iesk_inspection ii
JOIN lesiv.equipment e ON ii.equipment_id = e.id
JOIN lesiv.facility f ON e.facility_id = f.id
WHERE ii.server_modified_at > :modified_since
ORDER BY ii.server_modified_at;

-- name: get_by_id(id)^
-- Get IESK inspection by ID
SELECT id, equipment_id, inspector_id, started_at, completed_at, status, oil_level, bugs, dimensions, locks,
       stickers, comment, is_deleted, server_modified_at
FROM lesiv.iesk_inspection
WHERE id = :id;

-- name: get_iesk_inspections_by_plant_id(plant_id, modified_since)
-- Get all IESK inspections for plant (full data for aggregates)
-- :modified_since defaults to 1790-01-01 - only return inspections modified after that timestamp
SELECT ii.id, ii.equipment_id, ii.inspector_id, ii.started_at, ii.completed_at, ii.status, ii.oil_level, ii.bugs,
       ii.dimensions, ii.locks, ii.stickers, ii.comment, ii.is_deleted, ii.server_modified_at
FROM lesiv.iesk_inspection ii
JOIN lesiv.equipment e ON ii.equipment_id = e.id
JOIN lesiv.facility f ON e.facility_id = f.id
WHERE f.plant_id = :plant_id
  AND ii.server_modified_at > :modified_since
ORDER BY ii.server_modified_at;

-- name: get_iesk_image_links(iesk_inspection_id)
-- Get image links for IESK inspection (including logically deleted ones)
SELECT image_id, is_deleted
FROM lesiv.iesk_image
WHERE iesk_inspection_id = :iesk_inspection_id
ORDER BY image_id;

-- name: get_iesk_image_links_by_plant(plant_id, modified_since)
-- Get image links of the IESK inspections returned by get_iesk_inspections_by_plant_id (same filter)
SELECT im.iesk_inspection_id, im.image_id, im.is_deleted
FROM lesiv.iesk_image im
JOIN lesiv.iesk_inspection ii ON im.iesk_inspection_id = ii.id
JOIN lesiv.equipment e ON ii.equipment_id = e.id
JOIN lesiv.facility f ON e.facility_id = f.id
WHERE f.plant_id = :plant_id
  AND ii.server_modified_at > :modified_since
ORDER BY im.iesk_inspection_id, im.image_id;

-- name: upsert_iesk_inspection(id, equipment_id, inspector_id, started_at, completed_at, status, oil_level, bugs, dimensions, locks, stickers, comment, is_deleted, server_modified_at)!
-- Insert or update IESK inspection
INSERT INTO lesiv.iesk_inspection (id, equipment_id, inspector_id, started_at, completed_at, status, oil_level,
                                   bugs, dimensions, locks, stickers, comment, is_deleted, server_modified_at)
VALUES (:id, :equipment_id, :inspector_id, :started_at, :completed_at, :status, :oil_level,
        :bugs, :dimensions, :locks, :stickers, :comment, :is_deleted, :server_modified_at)
ON CONFLICT (id) DO UPDATE SET
    equipment_id = EXCLUDED.equipment_id,
    inspector_id = EXCLUDED.inspector_id,
    started_at = EXCLUDED.started_at,
    completed_at = EXCLUDED.completed_at,
    status = EXCLUDED.status,
    oil_level = EXCLUDED.oil_level,
    bugs = EXCLUDED.bugs,
    dimensions = EXCLUDED.dimensions,
    locks = EXCLUDED.locks,
    stickers = EXCLUDED.stickers,
    comment = EXCLUDED.comment,
    is_deleted = EXCLUDED.is_deleted,
    server_modified_at = EXCLUDED.server_modified_at;

-- name: upsert_iesk_image_link(iesk_inspection_id, image_id, is_deleted)!
-- Insert or update IESK image link
INSERT INTO lesiv.iesk_image (iesk_inspection_id, image_id, is_deleted)
VALUES (:iesk_inspection_id, :image_id, :is_deleted)
ON CONFLICT (iesk_inspection_id, image_id) DO UPDATE SET
    is_deleted = EXCLUDED.is_deleted;

-- name: mark_iesk_image_link_deleted(iesk_inspection_id, image_id)!
-- Mark IESK image link as deleted (logical deletion)
UPDATE lesiv.iesk_image
SET is_deleted = true
WHERE iesk_inspection_id = :iesk_inspection_id AND image_id = :image_id;

-- name: delete_iesk_inspection(id)!
-- Logically delete IESK inspection
UPDATE lesiv.iesk_inspection
SET is_deleted = true
WHERE id = :id;
