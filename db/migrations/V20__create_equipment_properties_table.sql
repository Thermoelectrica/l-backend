-- EquipmentProperties: equipment attributes that may be edited without claiming the plant.
--
-- Editing anything on the equipment aggregate goes through PUT /equipment, which requires the
-- caller's device to hold the pessimistic claim on the whole plant (see validate_equipment_ownership
-- in app/services/ownership_validator.py). That is far too coarse for a single scalar attribute:
-- setting one equipment's next inspection date would lock every other user out of every piece of
-- equipment on that plant until the claim goes stale at 03:00 Moscow time.
--
-- So these attributes live in their own aggregate with its own endpoints and no claim check - the
-- same split that was already made for equipment_defect.

CREATE TABLE lesiv.equipment_properties (
    -- 1:1 with equipment: the PK *is* the equipment id. No surrogate key, so there is no second
    -- UUID for the offline mobile client to generate and keep in sync, and the 1:1 cardinality is
    -- guaranteed by the primary key rather than by a unique index that someone could drop.
    equipment_id         UUID PRIMARY KEY,  -- Reference to equipment (no FK between aggregates)

    -- DATE rather than TIMESTAMPTZ: a calendar due date has no meaningful time or timezone.
    next_inspection_date DATE,

    server_modified_at   TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
    -- No is_deleted: an absent row and a row with all attributes NULL mean the same thing
    -- ("no properties set"), and clearing one property is done by setting it to NULL. The row's
    -- lifetime is bound to the equipment it describes.
);

COMMENT ON TABLE lesiv.equipment_properties IS
    'Equipment attributes editable without holding the plant claim. One row per equipment at most.';

COMMENT ON COLUMN lesiv.equipment_properties.equipment_id IS
    'Equipment this row describes. Also the primary key - the relation is 1:1.';

COMMENT ON COLUMN lesiv.equipment_properties.next_inspection_date IS
    'Calendar date this equipment is next due for inspection. NULL when not scheduled.';
