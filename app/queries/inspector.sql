-- name: get_all_inspectors(modified_since)
-- Get all inspectors (without password_hash for security)
-- :modified_since defaults to 1790-01-01 - only return inspectors modified after that timestamp
SELECT
    id,
    full_name,
    username,
    access_level,
    is_internal,
    server_modified_at
FROM lesiv.inspector
WHERE server_modified_at > :modified_since
ORDER BY server_modified_at;

-- name: get_by_id(id)^
SELECT
    id,
    full_name,
    username,
    password_hash,
    access_level,
    is_internal,
    server_modified_at
FROM lesiv.inspector
WHERE id = :id;
