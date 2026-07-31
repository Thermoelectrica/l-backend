-- name: get_by_id(id)^
-- Get work log by ID
SELECT id, started_at, completed_at, installation_percentage, 
       inspector_id, plant_id, is_deleted, server_modified_at
FROM lesiv.work_log
WHERE id = :id;

-- name: get_by_plant_id(plant_id, modified_since)
-- Get all work logs for plant (full data for aggregates)
-- :modified_since defaults to 1790-01-01 - only return work logs modified after that timestamp
SELECT wl.id, wl.started_at, wl.completed_at, wl.installation_percentage, 
       wl.inspector_id, wl.plant_id, wl.is_deleted, wl.server_modified_at,
       insp.username as inspector_username
FROM lesiv.work_log wl
LEFT JOIN lesiv.inspector insp ON wl.inspector_id = insp.id
WHERE wl.plant_id = :plant_id
  AND wl.server_modified_at > :modified_since
ORDER BY wl.server_modified_at;

-- name: get_inspectors_by_work_log(work_log_id)
-- Get all inspectors assigned to a work log
SELECT wli.inspector_id, insp.username, insp.full_name, wli.work_log_id
FROM lesiv.work_log_inspector wli
JOIN lesiv.inspector insp ON wli.inspector_id = insp.id
WHERE wli.work_log_id = :work_log_id
  AND insp.is_deleted = false;

-- name: upsert_work_log(id, started_at, completed_at, installation_percentage, inspector_id, plant_id, is_deleted, server_modified_at)!
-- Insert or update work log
INSERT INTO lesiv.work_log (id, started_at, completed_at, installation_percentage, 
                             inspector_id, plant_id, is_deleted, server_modified_at)
VALUES (:id, :started_at, :completed_at, :installation_percentage, 
        :inspector_id, :plant_id, :is_deleted, :server_modified_at)
ON CONFLICT (id) DO UPDATE SET
    started_at = EXCLUDED.started_at,
    completed_at = EXCLUDED.completed_at,
    installation_percentage = EXCLUDED.installation_percentage,
    inspector_id = EXCLUDED.inspector_id,
    plant_id = EXCLUDED.plant_id,
    is_deleted = EXCLUDED.is_deleted,
    server_modified_at = EXCLUDED.server_modified_at;

-- name: upsert_work_log_inspector(work_log_id, inspector_id)!
-- Insert or update work log - inspector relationship
INSERT INTO lesiv.work_log_inspector (work_log_id, inspector_id)
VALUES (:work_log_id, :inspector_id)
ON CONFLICT (work_log_id, inspector_id) DO UPDATE SET
    work_log_id = EXCLUDED.work_log_id,
    inspector_id = EXCLUDED.inspector_id;

-- name: delete_work_log_inspector(work_log_id, inspector_id)!
-- Delete work log - inspector relationship
DELETE FROM lesiv.work_log_inspector
WHERE work_log_id = :work_log_id AND inspector_id = :inspector_id;

-- name: delete_all_work_log_inspectors(work_log_id)!
-- Delete all inspectors for a work log
DELETE FROM lesiv.work_log_inspector
WHERE work_log_id = :work_log_id;

-- name: delete_work_log(work_log_id)!
-- Logically delete work log
UPDATE lesiv.work_log
SET is_deleted = true, server_modified_at = CURRENT_TIMESTAMP
WHERE id = :work_log_id;

-- name: restore_work_log(work_log_id)!
-- Restore logically deleted work log
UPDATE lesiv.work_log
SET is_deleted = false, server_modified_at = CURRENT_TIMESTAMP
WHERE id = :work_log_id;

-- name: get_all_work_logs(modified_since)
-- Get all work logs (lightweight list)
-- :modified_since defaults to 1790-01-01 - only return work logs modified after that timestamp
SELECT id, started_at, completed_at, installation_percentage, inspector_id, plant_id, is_deleted
FROM lesiv.work_log
WHERE server_modified_at > :modified_since
ORDER BY server_modified_at;
