-- Track which inspector created the plant.
-- NULL for plants created before this migration and for plants created while
-- auth is disabled (the anonymous user has no inspector row).
ALTER TABLE lesiv.plant ADD COLUMN created_by_user_id INTEGER;

ALTER TABLE lesiv.plant
    ADD CONSTRAINT fk_plant_created_by_user
        FOREIGN KEY (created_by_user_id) REFERENCES lesiv.inspector(id);

COMMENT ON COLUMN lesiv.plant.created_by_user_id IS
    'Inspector who created the plant. Set once on insert, never updated.';
