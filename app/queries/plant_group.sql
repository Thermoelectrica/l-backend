-- name: get_by_id(id)^
-- Get group by ID
SELECT id, name, parent_id, is_deleted, server_modified_at
FROM lesiv.plant_group
WHERE id = :id;

-- name: get_all_groups(modified_since)
-- Get all groups (lightweight list)
-- :modified_since defaults to 1790-01-01 - only return groups modified after that timestamp
SELECT id, name, parent_id, is_deleted, server_modified_at
FROM lesiv.plant_group
WHERE server_modified_at > :modified_since
ORDER BY server_modified_at;

-- name: get_plant_ids_by_group(plant_group_id)
-- Get all plant IDs that belong to a specific group
SELECT plant_id
FROM lesiv.plant_group_membership
WHERE plant_group_id = :plant_group_id;

-- name: get_all_memberships()
-- Get all plant_group_membership rows (used to attach plant_ids to all groups in one query)
SELECT plant_id, plant_group_id
FROM lesiv.plant_group_membership;

-- name: get_group_id_by_plant(plant_id)^
-- Get the group_id for a plant (to check if it already belongs to another group)
SELECT plant_group_id
FROM lesiv.plant_group_membership
WHERE plant_id = :plant_id;

-- name: upsert_membership(plant_id, plant_group_id)!
-- Insert or update plant group membership
INSERT INTO lesiv.plant_group_membership (plant_id, plant_group_id)
VALUES (:plant_id, :plant_group_id)
ON CONFLICT (plant_id) DO 
UPDATE SET
    plant_group_id = EXCLUDED.plant_group_id;

-- name: delete_membership_by_plant(plant_id)!
-- Remove a plant from its group
DELETE FROM lesiv.plant_group_membership
WHERE plant_id = :plant_id;

-- name: delete_memberships_by_group(plant_group_id)!
-- Remove all plants from a group (used during sync to clear before re-inserting)
DELETE FROM lesiv.plant_group_membership
WHERE plant_group_id = :plant_group_id;

-- name: check_cyclic_dependency(id, new_parent_id)^
-- Check if moving a group would create a cyclic dependency.
-- Traverses all ancestors of new_parent_id; if group appears among them,
-- moving group under new_parent_id would create a cycle.
WITH RECURSIVE ancestors AS (
    SELECT 
        id, parent_id
    FROM
        lesiv.plant_group
    WHERE 
        id = :new_parent_id
    UNION ALL
    SELECT g.id, g.parent_id
    FROM
        lesiv.plant_group g
        INNER JOIN ancestors a ON g.id = a.parent_id
)
SELECT 1 AS would_create_cycle
FROM ancestors
WHERE id = :id;

-- name: upsert_group(id, name, parent_id, is_deleted, server_modified_at)!
-- Insert or update group
INSERT INTO lesiv.plant_group (id, name, parent_id, is_deleted, server_modified_at)
VALUES (:id, :name, :parent_id, :is_deleted, :server_modified_at)
ON CONFLICT (id) DO
UPDATE SET
    name = EXCLUDED.name,
    parent_id = EXCLUDED.parent_id,
    is_deleted = EXCLUDED.is_deleted,
    server_modified_at = EXCLUDED.server_modified_at;
