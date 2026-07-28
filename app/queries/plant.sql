-- name: get_by_id(id)^
-- Get plant by ID
SELECT id, name, claimed_by_device_id, claimed_by_user_id, claimed_at, is_deleted, server_modified_at
FROM lesiv.plant
WHERE id = :id;

-- name: get_by_id_with_username(id)^
-- Get plant by ID with username of user who claimed it
SELECT p.id, p.name, p.claimed_by_device_id, p.claimed_by_user_id, p.claimed_at, p.is_deleted, p.server_modified_at,
    i.username as claimed_by_username
FROM lesiv.plant p
    LEFT JOIN lesiv.inspector i ON p.claimed_by_user_id = i.id
WHERE p.id = :id;

-- name: get_facilities(plant_id)
-- Get facilities for a plant
SELECT id, name, facility_template_id, is_deleted
FROM lesiv.facility
WHERE plant_id = :plant_id
ORDER BY name;

-- name: get_facility_ids(plant_id)
-- Get facility IDs for a plant
SELECT id
FROM lesiv.facility
WHERE plant_id = :plant_id;

-- name: get_equipment_ids_by_facility(facility_id)
-- Get equipment IDs for a facility
SELECT id
FROM lesiv.equipment
WHERE facility_id = :facility_id AND is_deleted = false;

-- name: get_facility_plant_id(facility_id)^
-- Get the plant_id for a facility (to check ownership)
SELECT plant_id
FROM lesiv.facility
WHERE id = :facility_id;

-- name: get_all_plants(modified_since)
-- Get all plants (lightweight list)
-- :modified_since defaults to 1790-01-01 - only return plants modified after that timestamp
SELECT id, name, is_deleted, claimed_by_device_id, claimed_by_user_id, claimed_at, server_modified_at
FROM lesiv.plant
WHERE server_modified_at > :modified_since
ORDER BY server_modified_at;

-- name: upsert_plant(id, name, is_deleted, server_modified_at)!
-- Insert or update plant (claim fields are managed separately via claim/release endpoints)
INSERT INTO lesiv.plant (id, name, is_deleted, server_modified_at)
VALUES (:id, :name, :is_deleted, :server_modified_at)
ON CONFLICT (id) DO UPDATE SET
    name = EXCLUDED.name,
    is_deleted = EXCLUDED.is_deleted,
    server_modified_at = EXCLUDED.server_modified_at;

-- name: upsert_facility(id, plant_id, name, facility_template_id, is_deleted)!
-- Insert or update facility
INSERT INTO lesiv.facility (id, plant_id, name, facility_template_id, is_deleted)
VALUES (:id, :plant_id, :name, :facility_template_id, :is_deleted)
ON CONFLICT (id) DO UPDATE SET
    name = EXCLUDED.name,
    facility_template_id = EXCLUDED.facility_template_id,
    is_deleted = EXCLUDED.is_deleted;

-- name: delete_plant(id)!
-- Logically delete plant
UPDATE lesiv.plant
SET is_deleted = true
WHERE id = :id;

-- name: mark_facility_deleted(id)!
-- Mark facility as deleted (logical deletion)
UPDATE lesiv.facility
SET is_deleted = true
WHERE id = :id;

-- name: claim_plant(id, device_id, user_id, claimed_at, server_modified_at)!
-- Claim plant for editing (updates server_modified_at for sync)
UPDATE lesiv.plant
SET claimed_by_device_id = :device_id,
    claimed_by_user_id = :user_id,
    claimed_at = :claimed_at,
    server_modified_at = :server_modified_at
WHERE id = :id;

-- name: release_plant(id, server_modified_at)!
-- Release plant (updates server_modified_at for sync)
UPDATE lesiv.plant
SET claimed_by_device_id = NULL,
    claimed_by_user_id = NULL,
    claimed_at = NULL,
    server_modified_at = :server_modified_at
WHERE id = :id;