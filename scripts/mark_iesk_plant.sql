-- Mark / unmark plants as IESK (lesiv.iesk_plant, see db/migrations/V24__iesk_inspection.sql).
-- Hand-written SQL: the app only reads lesiv.iesk_plant and there are no triggers in the database.
-- Run as a user with schema management rights (l_app_role has SELECT only on lesiv.iesk_plant).
--
-- Mobile reads the marker from GET /plant/all, which it always fetches in full, so the marker reaches
-- every device without touching the plant. Moving plant.server_modified_at is still recommended: it
-- also refreshes the local plant copy (PlantSynchronizer skips a plant whose timestamp did not change)
-- and incremental readers of /plant/all?modified_since. Each statement below does both at once.
--
-- Replace the UUID list. Running a statement twice is harmless.

-- Mark
WITH marked AS (
    INSERT INTO lesiv.iesk_plant (plant_id)
    SELECT unnest(ARRAY['00000000-0000-0000-0000-000000000000']::uuid[])
    ON CONFLICT (plant_id) DO NOTHING
    RETURNING plant_id
)
UPDATE lesiv.plant p
SET server_modified_at = clock_timestamp()
FROM marked
WHERE p.id = marked.plant_id;

-- Unmark
WITH unmarked AS (
    DELETE FROM lesiv.iesk_plant
    WHERE plant_id = ANY (ARRAY['00000000-0000-0000-0000-000000000000']::uuid[])
    RETURNING plant_id
)
UPDATE lesiv.plant p
SET server_modified_at = clock_timestamp()
FROM unmarked
WHERE p.id = unmarked.plant_id;
