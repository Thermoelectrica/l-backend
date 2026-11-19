-- IESK inspection aggregate queries (root lesiv.iesk_inspection + links lesiv.iesk_inspection_image_link)

-- name: get_all_iesk_inspections(modified_since)
-- Get all IESK inspections (lightweight list)
-- plant_id is returned so the router can filter by accessible plants in one pass
-- :modified_since defaults to 1790-01-01 - only return inspections modified after that timestamp
SELECT ii.id, ii.equipment_id, ii.inspector_id, ii.created_at, ii.is_deleted, ii.server_modified_at, f.plant_id
FROM lesiv.iesk_inspection ii
JOIN lesiv.equipment e ON ii.equipment_id = e.id
JOIN lesiv.facility f ON e.facility_id = f.id
WHERE ii.server_modified_at > :modified_since
ORDER BY ii.server_modified_at;

-- name: get_by_id(id)^
-- Get IESK inspection by ID
SELECT id, equipment_id, inspector_id, created_at, oil_level, bugs, dimensions, locks,
       stickers, comment, is_deleted, server_modified_at
FROM lesiv.iesk_inspection
WHERE id = :id;

-- name: get_iesk_inspections_by_plant_id(plant_id, modified_since)
-- Get all IESK inspections for plant (full data for aggregates)
-- :modified_since defaults to 1790-01-01 - only return inspections modified after that timestamp
SELECT ii.id, ii.equipment_id, ii.inspector_id, ii.created_at, ii.oil_level, ii.bugs,
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
FROM lesiv.iesk_inspection_image_link
WHERE iesk_inspection_id = :iesk_inspection_id
ORDER BY image_id;

-- name: get_iesk_image_links_by_plant(plant_id, modified_since)
-- Get image links of the IESK inspections returned by get_iesk_inspections_by_plant_id (same filter)
SELECT il.iesk_inspection_id, il.image_id, il.is_deleted
FROM lesiv.iesk_inspection_image_link il
JOIN lesiv.iesk_inspection ii ON il.iesk_inspection_id = ii.id
JOIN lesiv.equipment e ON ii.equipment_id = e.id
JOIN lesiv.facility f ON e.facility_id = f.id
WHERE f.plant_id = :plant_id
  AND ii.server_modified_at > :modified_since
ORDER BY il.iesk_inspection_id, il.image_id;

-- name: upsert_iesk_inspection(id, equipment_id, inspector_id, created_at, oil_level, bugs, dimensions, locks, stickers, comment, is_deleted, server_modified_at)!
-- Insert or update IESK inspection
-- created_at is intentionally absent from DO UPDATE: it is set once on creation and never changed afterwards.
INSERT INTO lesiv.iesk_inspection (id, equipment_id, inspector_id, created_at, oil_level,
                                   bugs, dimensions, locks, stickers, comment, is_deleted, server_modified_at)
VALUES (:id, :equipment_id, :inspector_id, :created_at, :oil_level,
        :bugs, :dimensions, :locks, :stickers, :comment, :is_deleted, :server_modified_at)
ON CONFLICT (id) DO UPDATE SET
    equipment_id = EXCLUDED.equipment_id,
    inspector_id = EXCLUDED.inspector_id,
    oil_level = EXCLUDED.oil_level,
    bugs = EXCLUDED.bugs,
    dimensions = EXCLUDED.dimensions,
    locks = EXCLUDED.locks,
    stickers = EXCLUDED.stickers,
    comment = EXCLUDED.comment,
    is_deleted = EXCLUDED.is_deleted,
    server_modified_at = EXCLUDED.server_modified_at;

-- name: upsert_iesk_image_link(image_id, iesk_inspection_id, is_deleted)!
-- Insert or update IESK inspection image link
INSERT INTO lesiv.iesk_inspection_image_link (image_id, iesk_inspection_id, is_deleted)
VALUES (:image_id, :iesk_inspection_id, :is_deleted)
ON CONFLICT (image_id, iesk_inspection_id) DO UPDATE SET
    is_deleted = EXCLUDED.is_deleted;

-- name: mark_iesk_image_link_deleted(image_id, iesk_inspection_id)!
-- Mark IESK inspection image link as deleted (logical deletion)
UPDATE lesiv.iesk_inspection_image_link
SET is_deleted = true
WHERE image_id = :image_id AND iesk_inspection_id = :iesk_inspection_id;

-- name: delete_iesk_inspection(id)!
-- Logically delete IESK inspection
UPDATE lesiv.iesk_inspection
SET is_deleted = true
WHERE id = :id;
