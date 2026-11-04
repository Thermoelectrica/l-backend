-- Rename equipment_properties -> equipment_property (all table names are singular).
--
-- Also replace the unused next_inspection_date with inspection_schedule_id. The real next
-- inspection date is computed dynamically from the last visit date and defect severity, so the
-- schedule is stored as a reference to the inspection_schedule dictionary instead of a fixed date.

ALTER TABLE lesiv.equipment_properties RENAME TO equipment_property;

-- The equipment_detailed_view references next_inspection_date. Drop it here so the column can be
-- removed; R__equipment_detailed_view.sql recreates it (with inspection_schedule_id) later in the
-- same Flyway invocation.
DROP VIEW IF EXISTS lesiv.equipment_detailed_view;

ALTER TABLE lesiv.equipment_property DROP COLUMN next_inspection_date;

-- Reference to inspection_schedule (no FK between aggregates, same as defect_type_id)
ALTER TABLE lesiv.equipment_property ADD COLUMN inspection_schedule_id INTEGER;

COMMENT ON TABLE lesiv.equipment_property IS
    'Equipment attributes editable without holding the plant claim. One row per equipment at most.';

COMMENT ON COLUMN lesiv.equipment_property.equipment_id IS
    'Equipment this row describes. Also the primary key - the relation is 1:1.';

COMMENT ON COLUMN lesiv.equipment_property.inspection_schedule_id IS
    'Reference to the inspection_schedule dictionary that drives when this equipment is next due for inspection. NULL when not scheduled.';