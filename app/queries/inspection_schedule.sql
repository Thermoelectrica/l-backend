-- name: get_all_inspection_schedules(modified_since)
-- Get all inspection schedules
-- :modified_since defaults to 1790-01-01 - only return inspection schedules modified after that timestamp
SELECT id, name, default_interval, severity1_interval, severity2_interval, severity3_interval, alert_interval, is_deleted, server_modified_at
FROM lesiv.inspection_schedule
WHERE server_modified_at > :modified_since
ORDER BY server_modified_at;