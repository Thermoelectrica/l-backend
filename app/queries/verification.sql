-- Verification aggregate SQL queries

-- name: get_verification_by_id(id)^
-- Get verification by ID
SELECT
    id, inspection_step_id, plant_id, inspector_id, verifier_id, status,
    server_modified_at, is_deleted, step_type, defect_id, unit_name, description,
    is_resolved, sticker_type_id, t_sticker, t_environment, t_similar_unit, epsilon,
    t_observed, measured_current, nominal_current, defect_type_id, is_sticker_present,
    is_test_ready, is_attention_required
FROM lesiv.verification
WHERE id = :id;

-- name: get_verification_image_links(verification_id)
-- Get image links for verification
SELECT image_id, is_deleted
FROM lesiv.verification_image_link
WHERE verification_id = :verification_id
ORDER BY image_id;

-- name: get_verification_events(verification_id)
-- Get events for verification
SELECT id, verification_id, event_type, inspector_id, comment, created_at
FROM lesiv.verification_event
WHERE verification_id = :verification_id
ORDER BY created_at;

-- name: get_verifications_by_inspector(inspector_id, modified_since)
-- Get all verifications where inspector_id matches (submitted_by_me)
SELECT
    id, inspection_step_id, plant_id, inspector_id, verifier_id, status,
    server_modified_at, is_deleted, step_type, defect_id, unit_name, description,
    is_resolved, sticker_type_id, t_sticker, t_environment, t_similar_unit, epsilon,
    t_observed, measured_current, nominal_current, defect_type_id, is_sticker_present,
    is_test_ready, is_attention_required
FROM lesiv.verification
WHERE inspector_id = :inspector_id
  AND server_modified_at > :modified_since
ORDER BY server_modified_at DESC;

-- name: get_verifications_by_verifier(verifier_id, modified_since)
-- Get all verifications where verifier_id matches (assigned_to_me)
SELECT
    id, inspection_step_id, plant_id, inspector_id, verifier_id, status,
    server_modified_at, is_deleted, step_type, defect_id, unit_name, description,
    is_resolved, sticker_type_id, t_sticker, t_environment, t_similar_unit, epsilon,
    t_observed, measured_current, nominal_current, defect_type_id, is_sticker_present,
    is_test_ready, is_attention_required
FROM lesiv.verification
WHERE verifier_id = :verifier_id
  AND server_modified_at > :modified_since
ORDER BY server_modified_at DESC;

-- name: get_active_verification_by_step(inspection_step_id)^
-- Check if active (non-APPROVED, non-deleted) verification exists for step
SELECT id, status
FROM lesiv.verification
WHERE inspection_step_id = :inspection_step_id
  AND status != 'APPROVED'
  AND NOT is_deleted
LIMIT 1;

-- name: get_inspection_step_data(step_id)^
-- Get inspection step data for copying to verification
SELECT
    s.id, s.inspection_id, s.step_type, s.defect_id, s.unit_name, s.description,
    s.is_resolved, s.sticker_type_id, s.t_sticker, s.t_environment, s.t_similar_unit,
    s.epsilon, s.t_observed, s.measured_current, s.nominal_current, s.defect_type_id,
    s.is_sticker_present, s.is_test_ready, s.is_attention_required, s.is_deleted,
    i.equipment_id, e.facility_id, f.plant_id
FROM lesiv.inspection_step s
JOIN lesiv.inspection i ON s.inspection_id = i.id
JOIN lesiv.equipment e ON i.equipment_id = e.id
JOIN lesiv.facility f ON e.facility_id = f.id
WHERE s.id = :step_id;

-- name: get_inspection_step_image_links(step_id)
-- Get image links for inspection step (to copy to verification)
SELECT image_id, is_deleted
FROM lesiv.inspection_image_link
WHERE inspection_step_id = :step_id
ORDER BY image_id;

-- name: insert_verification(id, inspection_step_id, plant_id, inspector_id, verifier_id, status, server_modified_at, step_type, defect_id, unit_name, description, is_resolved, sticker_type_id, t_sticker, t_environment, t_similar_unit, epsilon, t_observed, measured_current, nominal_current, defect_type_id, is_sticker_present, is_test_ready, is_attention_required)!
-- Insert new verification
INSERT INTO lesiv.verification (
    id, inspection_step_id, plant_id, inspector_id, verifier_id, status, server_modified_at,
    step_type, defect_id, unit_name, description, is_resolved, sticker_type_id, t_sticker,
    t_environment, t_similar_unit, epsilon, t_observed, measured_current, nominal_current,
    defect_type_id, is_sticker_present, is_test_ready, is_attention_required
) VALUES (
    :id, :inspection_step_id, :plant_id, :inspector_id, :verifier_id, :status, :server_modified_at,
    :step_type, :defect_id, :unit_name, :description, :is_resolved, :sticker_type_id, :t_sticker,
    :t_environment, :t_similar_unit, :epsilon, :t_observed, :measured_current, :nominal_current,
    :defect_type_id, :is_sticker_present, :is_test_ready, :is_attention_required
);

-- name: update_verification(id, verifier_id, server_modified_at, step_type, defect_id, unit_name, description, is_resolved, sticker_type_id, t_sticker, t_environment, t_similar_unit, epsilon, t_observed, measured_current, nominal_current, defect_type_id, is_sticker_present, is_test_ready, is_attention_required)!
-- Update verification data and verifier
UPDATE lesiv.verification SET
    verifier_id = :verifier_id,
    server_modified_at = :server_modified_at,
    step_type = :step_type,
    defect_id = :defect_id,
    unit_name = :unit_name,
    description = :description,
    is_resolved = :is_resolved,
    sticker_type_id = :sticker_type_id,
    t_sticker = :t_sticker,
    t_environment = :t_environment,
    t_similar_unit = :t_similar_unit,
    epsilon = :epsilon,
    t_observed = :t_observed,
    measured_current = :measured_current,
    nominal_current = :nominal_current,
    defect_type_id = :defect_type_id,
    is_sticker_present = :is_sticker_present,
    is_test_ready = :is_test_ready,
    is_attention_required = :is_attention_required
WHERE id = :id;

-- name: update_verification_status(id, status)!
-- Update verification status
UPDATE lesiv.verification SET status = :status WHERE id = :id;

-- name: bump_verification_server_modified_at(id, server_modified_at)!
-- Update server_modified_at for verification
UPDATE lesiv.verification SET server_modified_at = :server_modified_at WHERE id = :id;

-- name: upsert_verification_image_link(verification_id, image_id, is_deleted)!
-- Insert or update verification image link
INSERT INTO lesiv.verification_image_link (verification_id, image_id, is_deleted)
VALUES (:verification_id, :image_id, :is_deleted)
ON CONFLICT (verification_id, image_id) DO UPDATE SET
    is_deleted = EXCLUDED.is_deleted;

-- name: get_verification_image_link_ids(verification_id)
-- Get image link IDs for verification (for sync)
SELECT image_id, is_deleted
FROM lesiv.verification_image_link
WHERE verification_id = :verification_id;

-- name: mark_verification_image_link_deleted(verification_id, image_id)!
-- Mark verification image link as deleted
UPDATE lesiv.verification_image_link
SET is_deleted = true
WHERE verification_id = :verification_id AND image_id = :image_id;

-- name: insert_verification_event(verification_id, event_type, inspector_id, comment)!
-- Insert verification event
INSERT INTO lesiv.verification_event (verification_id, event_type, inspector_id, comment)
VALUES (:verification_id, :event_type, :inspector_id, :comment);

-- name: copy_back_to_inspection_step(step_id, step_type, defect_id, unit_name, description, is_resolved, sticker_type_id, t_sticker, t_environment, t_similar_unit, epsilon, t_observed, measured_current, nominal_current, defect_type_id, is_sticker_present, is_test_ready, is_attention_required, verified_by, verified_at)!
-- Copy verification data back to inspection step on approval
UPDATE lesiv.inspection_step SET
    step_type = :step_type,
    defect_id = :defect_id,
    unit_name = :unit_name,
    description = :description,
    is_resolved = :is_resolved,
    sticker_type_id = :sticker_type_id,
    t_sticker = :t_sticker,
    t_environment = :t_environment,
    t_similar_unit = :t_similar_unit,
    epsilon = :epsilon,
    t_observed = :t_observed,
    measured_current = :measured_current,
    nominal_current = :nominal_current,
    defect_type_id = :defect_type_id,
    is_sticker_present = :is_sticker_present,
    is_test_ready = :is_test_ready,
    is_attention_required = :is_attention_required,
    verified_by = :verified_by,
    verified_at = :verified_at
WHERE id = :step_id;

-- name: copy_back_inspection_image_links(inspection_step_id)!
-- Delete existing inspection image links (will be replaced by verification links)
DELETE FROM lesiv.inspection_image_link WHERE inspection_step_id = :inspection_step_id;

-- name: insert_inspection_image_link_from_verification(inspection_step_id, image_id, is_deleted)!
-- Insert image link from verification to inspection step
INSERT INTO lesiv.inspection_image_link (inspection_step_id, image_id, is_deleted)
VALUES (:inspection_step_id, :image_id, :is_deleted);

-- name: bump_inspection_server_modified_at(inspection_id, server_modified_at)!
-- Bump inspection server_modified_at to trigger client sync
UPDATE lesiv.inspection SET server_modified_at = :server_modified_at WHERE id = :inspection_id;

-- name: get_inspector_access_level(inspector_id)^
-- Get inspector access level for validation
SELECT id, access_level, is_deleted
FROM lesiv.inspector
WHERE id = :inspector_id;
