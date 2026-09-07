-- name: get_all_inspections(modified_since)
-- Get all inspections (lightweight list)
-- :modified_since defaults to 1790-01-01 - only return inspections modified after that timestamp
SELECT id, equipment_id, inspector_id, started_at, completed_at, status, is_deleted
FROM lesiv.inspection
WHERE server_modified_at > :modified_since
ORDER BY server_modified_at;

-- name: get_by_plant_id(plant_id, modified_since)
-- Get all inspections for plant (full data for aggregates)
-- :modified_since defaults to 1790-01-01 - only return inspections modified after that timestamp
SELECT i.id, i.equipment_id, i.inspector_id, i.started_at, i.completed_at, i.status, i.is_deleted, i.server_modified_at
FROM lesiv.inspection i
JOIN lesiv.equipment e ON i.equipment_id = e.id
JOIN lesiv.facility f ON e.facility_id = f.id
WHERE f.plant_id = :plant_id
  AND i.server_modified_at > :modified_since
ORDER BY i.server_modified_at;

-- name: get_steps_by_plant(plant_id)
-- Get all inspection steps for inspections of a plant
SELECT s.id, s.started_at, s.inspection_id, s.step_number, s.step_type, s.defect_id,
       s.unit_name, s.description, s.is_resolved, s.sticker_type_id, s.t_sticker,
       s.t_environment, s.t_similar_unit, s.epsilon,
       s.t_observed, s.measured_current, s.nominal_current, s.defect_type_id, s.is_sticker_present,
       s.is_test_ready, s.is_attention_required, s.verified_by, s.verified_at, s.step_status, s.is_deleted
FROM lesiv.inspection_step s
JOIN lesiv.inspection i ON s.inspection_id = i.id
JOIN lesiv.equipment e ON i.equipment_id = e.id
JOIN lesiv.facility f ON e.facility_id = f.id
WHERE f.plant_id = :plant_id
ORDER BY s.inspection_id, s.step_number;

-- name: get_image_links_by_plant(plant_id)
-- Get all image links for inspection steps of a plant
SELECT il.image_id, il.inspection_step_id, il.is_deleted
FROM lesiv.inspection_image_link il
JOIN lesiv.inspection_step s ON il.inspection_step_id = s.id
JOIN lesiv.inspection i ON s.inspection_id = i.id
JOIN lesiv.equipment e ON i.equipment_id = e.id
JOIN lesiv.facility f ON e.facility_id = f.id
WHERE f.plant_id = :plant_id
ORDER BY il.inspection_step_id;

-- name: get_by_id(id)^
-- Get inspection by ID
SELECT id, equipment_id, inspector_id, started_at, completed_at, status, is_deleted, server_modified_at
FROM lesiv.inspection
WHERE id = :id;

-- name: get_by_id_with_username(id)^
-- Get inspection by ID with username of inspector who created it
SELECT i.id, i.equipment_id, i.inspector_id, i.started_at, i.completed_at, i.status, i.is_deleted, i.server_modified_at,
       insp.username as inspector_username
FROM lesiv.inspection i
LEFT JOIN lesiv.inspector insp ON i.inspector_id = insp.id
WHERE i.id = :id;

-- name: get_steps(inspection_id)
-- Get steps for inspection
SELECT id, started_at, inspection_id, step_number, step_type, defect_id,
       unit_name, description, is_resolved, sticker_type_id, t_sticker,
       t_environment, t_similar_unit, epsilon,
       t_observed, measured_current, nominal_current, defect_type_id, is_sticker_present,
       is_test_ready, is_attention_required, verified_by, verified_at, step_status, is_deleted
FROM lesiv.inspection_step
WHERE inspection_id = :inspection_id
ORDER BY step_number;

-- name: get_step_ids(inspection_id)
-- Get step IDs for inspection (for sync)
SELECT id
FROM lesiv.inspection_step
WHERE inspection_id = :inspection_id;

-- name: get_step_inspection_id(step_id)^
-- Get the inspection_id for a step (to check ownership)
SELECT inspection_id
FROM lesiv.inspection_step
WHERE id = :step_id;

-- name: get_image_links(inspection_step_id)
-- Get image links for inspection step
SELECT image_id, is_deleted
FROM lesiv.inspection_image_link
WHERE inspection_step_id = :inspection_step_id
ORDER BY image_id;

-- name: get_image_link_ids(inspection_step_id)
-- Get image link IDs for inspection step (for sync)
SELECT image_id, is_deleted
FROM lesiv.inspection_image_link
WHERE inspection_step_id = :inspection_step_id;

-- name: upsert_inspection(id, equipment_id, inspector_id, started_at, completed_at, status, is_deleted, server_modified_at)!
-- Insert or update inspection
INSERT INTO lesiv.inspection (id, equipment_id, inspector_id, started_at, completed_at,
                               status, is_deleted, server_modified_at)
VALUES (:id, :equipment_id, :inspector_id, :started_at, :completed_at,
        :status, :is_deleted, :server_modified_at)
ON CONFLICT (id) DO UPDATE SET
    equipment_id = EXCLUDED.equipment_id,
    inspector_id = EXCLUDED.inspector_id,
    started_at = EXCLUDED.started_at,
    completed_at = EXCLUDED.completed_at,
    status = EXCLUDED.status,
    is_deleted = EXCLUDED.is_deleted,
    server_modified_at = EXCLUDED.server_modified_at;

-- name: upsert_step(id, started_at, inspection_id, step_number, step_type, defect_id, unit_name, description, is_resolved, sticker_type_id, t_sticker, t_environment, t_similar_unit, epsilon, t_observed, measured_current, nominal_current, defect_type_id, is_sticker_present, is_test_ready, is_attention_required, step_status, is_deleted)!
-- Insert or update inspection step
INSERT INTO lesiv.inspection_step (id, started_at, inspection_id, step_number, step_type,
                                    defect_id, unit_name, description, is_resolved, sticker_type_id,
                                    t_sticker, t_environment, t_similar_unit, epsilon,
                                    t_observed, measured_current, nominal_current, defect_type_id, is_sticker_present,
                                    is_test_ready, is_attention_required, step_status, is_deleted)
VALUES (:id, :started_at, :inspection_id, :step_number, :step_type,
        :defect_id, :unit_name, :description, :is_resolved, :sticker_type_id,
        :t_sticker, :t_environment, :t_similar_unit, :epsilon,
        :t_observed, :measured_current, :nominal_current, :defect_type_id, :is_sticker_present,
        :is_test_ready, :is_attention_required, :step_status, :is_deleted)
ON CONFLICT (id) DO UPDATE SET
    started_at = EXCLUDED.started_at,
    inspection_id = EXCLUDED.inspection_id,
    step_number = EXCLUDED.step_number,
    step_type = EXCLUDED.step_type,
    defect_id = EXCLUDED.defect_id,
    unit_name = EXCLUDED.unit_name,
    description = EXCLUDED.description,
    is_resolved = EXCLUDED.is_resolved,
    sticker_type_id = EXCLUDED.sticker_type_id,
    t_sticker = EXCLUDED.t_sticker,
    t_environment = EXCLUDED.t_environment,
    t_similar_unit = EXCLUDED.t_similar_unit,
    epsilon = EXCLUDED.epsilon,
    t_observed = EXCLUDED.t_observed,
    measured_current = EXCLUDED.measured_current,
    nominal_current = EXCLUDED.nominal_current,
    defect_type_id = EXCLUDED.defect_type_id,
    is_sticker_present = EXCLUDED.is_sticker_present,
    is_test_ready = EXCLUDED.is_test_ready,
    is_attention_required = EXCLUDED.is_attention_required,
    step_status = EXCLUDED.step_status,
    is_deleted = EXCLUDED.is_deleted;

-- name: upsert_image_link(image_id, inspection_step_id, is_deleted)!
-- Insert or update image link
INSERT INTO lesiv.inspection_image_link (image_id, inspection_step_id, is_deleted)
VALUES (:image_id, :inspection_step_id, :is_deleted)
ON CONFLICT (image_id, inspection_step_id) DO UPDATE SET
    is_deleted = EXCLUDED.is_deleted;

-- name: delete_inspection(id)!
-- Logically delete inspection
UPDATE lesiv.inspection
SET is_deleted = true
WHERE id = :id;

-- name: mark_step_deleted(id)!
-- Mark inspection step as deleted (logical deletion)
UPDATE lesiv.inspection_step
SET is_deleted = true
WHERE id = :id;

-- name: mark_image_link_deleted(image_id, inspection_step_id)!
-- Mark image link as deleted (logical deletion)
UPDATE lesiv.inspection_image_link
SET is_deleted = true
WHERE image_id = :image_id AND inspection_step_id = :inspection_step_id;
