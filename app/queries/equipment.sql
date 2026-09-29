-- name: get_all_equipment(modified_since)
-- Get all equipment (lightweight list)
-- :modified_since defaults to 1790-01-01 - only return equipment modified after that timestamp
SELECT id, facility_id, parent_id, name, qr_code, is_container, equipment_type_id, facility_template_equipment_id, is_deleted
FROM lesiv.equipment
WHERE server_modified_at > :modified_since
ORDER BY server_modified_at;

-- name: get_by_plant_id(plant_id, modified_since)
-- Get all equipment for a plant (full data for aggregates) - joins through facility
-- :modified_since defaults to 1790-01-01 - only return equipment modified after that timestamp
SELECT e.id, e.facility_id, e.parent_id, e.name, e.qr_code, e.tag_code, e.is_container, e.equipment_type_id,
       e.facility_template_equipment_id, e.estimated_point_count, e.is_deleted, e.server_modified_at
FROM lesiv.equipment e
JOIN lesiv.facility f ON e.facility_id = f.id
WHERE f.plant_id = :plant_id
  AND e.server_modified_at > :modified_since
ORDER BY e.server_modified_at;

-- name: get_control_points_by_plant(plant_id)
-- Get all control points for equipment in a plant
SELECT cp.id, cp.equipment_id, cp.control_point_type, cp.point_count, cp.sticker_count,
       cp.sticker_type_id, cp.is_deleted
FROM lesiv.equipment_control_point cp
JOIN lesiv.equipment e ON cp.equipment_id = e.id
JOIN lesiv.facility f ON e.facility_id = f.id
WHERE f.plant_id = :plant_id
ORDER BY cp.equipment_id, cp.control_point_type;

-- name: get_inspections_by_plant(plant_id)
-- Get all inspection IDs for equipment in a plant
SELECT i.id, i.equipment_id
FROM lesiv.inspection i
JOIN lesiv.equipment e ON i.equipment_id = e.id
JOIN lesiv.facility f ON e.facility_id = f.id
WHERE f.plant_id = :plant_id AND i.is_deleted = false
ORDER BY i.equipment_id, i.started_at DESC;

-- name: get_by_id(id)^
-- Get equipment by ID
SELECT id, facility_id, parent_id, name, qr_code, tag_code, is_container, equipment_type_id,
       facility_template_equipment_id, estimated_point_count, is_deleted, server_modified_at
FROM lesiv.equipment
WHERE id = :id;

-- name: get_control_points(equipment_id)
-- Get control points for equipment
SELECT id, equipment_id, control_point_type, point_count, sticker_count,
       sticker_type_id, is_deleted
FROM lesiv.equipment_control_point
WHERE equipment_id = :equipment_id
ORDER BY control_point_type;

-- DEPRECATED: Defect queries removed - use defect router instead
-- get_defects_by_plant, get_defects, get_defect_ids, get_defect_equipment_id, upsert_defect, mark_defect_deleted
-- are no longer needed as defects are managed separately

-- name: get_control_point_ids(equipment_id)
-- Get control point IDs for equipment (for sync)
SELECT id
FROM lesiv.equipment_control_point
WHERE equipment_id = :equipment_id;

-- name: get_control_point_equipment_id(control_point_id)^
-- Get the equipment_id for a control point (to check ownership)
SELECT equipment_id
FROM lesiv.equipment_control_point
WHERE id = :control_point_id;

-- name: get_inspection_ids(equipment_id)
-- Get inspection IDs for equipment
SELECT id, equipment_id
FROM lesiv.inspection
WHERE equipment_id = :equipment_id AND is_deleted = false
ORDER BY started_at DESC;

-- name: get_plant_claim_info_for_equipment(equipment_id)^
-- Get plant claim info for equipment (joins through facility to plant)
SELECT p.id as plant_id, p.claimed_by_user_id, p.claimed_by_device_id, p.claimed_at,
       i.username as claimed_by_username
FROM lesiv.equipment e
JOIN lesiv.facility f ON e.facility_id = f.id
JOIN lesiv.plant p ON f.plant_id = p.id
LEFT JOIN lesiv.inspector i ON p.claimed_by_user_id = i.id
WHERE e.id = :equipment_id;

-- name: upsert_equipment(id, facility_id, parent_id, name, qr_code, tag_code, is_container, equipment_type_id, facility_template_equipment_id, estimated_point_count, is_deleted, server_modified_at)!
-- Insert or update equipment
INSERT INTO lesiv.equipment (id, facility_id, parent_id, name, qr_code, tag_code, is_container,
                             equipment_type_id, facility_template_equipment_id, estimated_point_count,
                             is_deleted, server_modified_at)
VALUES (:id, :facility_id, :parent_id, :name, :qr_code, :tag_code, :is_container,
        :equipment_type_id, :facility_template_equipment_id, :estimated_point_count,
        :is_deleted, :server_modified_at)
ON CONFLICT (id) DO UPDATE SET
    facility_id = EXCLUDED.facility_id,
    parent_id = EXCLUDED.parent_id,
    name = EXCLUDED.name,
    qr_code = EXCLUDED.qr_code,
    tag_code = EXCLUDED.tag_code,
    is_container = EXCLUDED.is_container,
    equipment_type_id = EXCLUDED.equipment_type_id,
    facility_template_equipment_id = EXCLUDED.facility_template_equipment_id,
    estimated_point_count = EXCLUDED.estimated_point_count,
    is_deleted = EXCLUDED.is_deleted,
    server_modified_at = EXCLUDED.server_modified_at;

-- name: upsert_control_point(id, equipment_id, control_point_type, point_count, sticker_count, sticker_type_id, is_deleted)!
-- Insert or update control point (match by ID, not by equipment_id + control_point_type)
INSERT INTO lesiv.equipment_control_point (id, equipment_id, control_point_type,
                                           point_count, sticker_count, sticker_type_id,
                                           is_deleted)
VALUES (:id, :equipment_id, :control_point_type,
        :point_count, :sticker_count, :sticker_type_id,
        :is_deleted)
ON CONFLICT (id) DO UPDATE SET
    equipment_id = EXCLUDED.equipment_id,
    control_point_type = EXCLUDED.control_point_type,
    point_count = EXCLUDED.point_count,
    sticker_count = EXCLUDED.sticker_count,
    sticker_type_id = EXCLUDED.sticker_type_id,
    is_deleted = EXCLUDED.is_deleted;

-- name: delete_equipment(id)!
-- Logically delete equipment
UPDATE lesiv.equipment
SET is_deleted = true
WHERE id = :id;

-- name: mark_control_point_deleted(id)!
-- Mark control point as deleted (logical deletion)
UPDATE lesiv.equipment_control_point
SET is_deleted = true
WHERE id = :id;