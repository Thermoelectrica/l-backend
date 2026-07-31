-- name: get_all_equipment_types(modified_since)
-- Get all equipment types
-- :modified_since defaults to 1790-01-01 - only return equipment types modified after that timestamp
SELECT id, name, is_deleted, server_modified_at
FROM lesiv.equipment_type
WHERE server_modified_at > :modified_since
ORDER BY server_modified_at;

-- name: get_all_control_point_templates()
-- Get all control point templates
SELECT id, equipment_type_id, name, short_name, default_sticker_id, is_deleted
FROM lesiv.equipment_control_point_template
ORDER BY equipment_type_id, name;


-- name: get_control_point_templates(equipment_type_id)
-- Get control point templates for specific equipment_type
SELECT id, equipment_type_id, name, short_name, default_sticker_id, is_deleted
FROM lesiv.equipment_control_point_template
WHERE equipment_type_id = :equipment_type_id
ORDER BY equipment_type_id, name;

-- name: get_by_id(id)^
-- Get a single equipment type by id
SELECT id, name, is_deleted, server_modified_at
FROM lesiv.equipment_type
WHERE id = :id;

-- name: get_template_ids(equipment_type_id)
-- Get IDs of all control point templates for a given equipment type
SELECT id
FROM lesiv.equipment_control_point_template
WHERE equipment_type_id = :equipment_type_id;

-- name: upsert_equipment_type(id, name)!
-- Insert or update an equipment type; updates server_modified_at on conflict
INSERT INTO lesiv.equipment_type
    (id, name, server_modified_at)
VALUES
    (:id, :name, CURRENT_TIMESTAMP)
ON CONFLICT
(id) DO
UPDATE
    SET name = EXCLUDED.name,
        server_modified_at = CURRENT_TIMESTAMP;

-- name: delete_equipment_type(id)!
-- Delete an equipment type by id
DELETE FROM lesiv.equipment_type
WHERE id = :id;

-- name: upsert_template(id, equipment_type_id, name, short_name, default_sticker_id)!
-- Insert or update a control point template
INSERT INTO lesiv.equipment_control_point_template
    (id, equipment_type_id, name, short_name, default_sticker_id)
VALUES
    (:id, :equipment_type_id, :name, :short_name, :default_sticker_id)
ON CONFLICT
(id) DO
UPDATE
    SET equipment_type_id = EXCLUDED.equipment_type_id,
        name              = EXCLUDED.name,
        short_name        = EXCLUDED.short_name,
        default_sticker_id = EXCLUDED.default_sticker_id;

-- name: delete_template(id)!
-- Delete a control point template by id
DELETE FROM lesiv.equipment_control_point_template
WHERE id = :id;