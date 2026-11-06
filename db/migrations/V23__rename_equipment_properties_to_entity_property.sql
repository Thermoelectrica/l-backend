-- Rename equipment_properties -> entity_property (all table names are singular).
--
-- The aggregate no longer describes only equipment: the same claim-free attributes apply to any
-- schedulable entity, so the row is keyed by a polymorphic reference - entity_id plus entity_type
-- ('plant', 'facility' or 'equipment') - instead of a bare equipment_id.
--
-- Also replace the unused next_inspection_date with inspection_schedule_id. The real next
-- inspection date is computed dynamically from the last visit date and defect severity, so the
-- schedule is stored as a reference to the inspection_schedule dictionary instead of a fixed date.

CREATE TYPE lesiv.entity_type AS ENUM ('plant', 'facility', 'equipment');

ALTER TABLE lesiv.equipment_properties RENAME TO entity_property;

-- The equipment_detailed_view references next_inspection_date. Drop it here so the column can be
-- removed; R__equipment_detailed_view.sql recreates it (with inspection_schedule_id) later in the
-- same Flyway invocation.
DROP VIEW IF EXISTS lesiv.equipment_detailed_view;

ALTER TABLE lesiv.entity_property DROP COLUMN next_inspection_date;

-- Reference to inspection_schedule (no FK between aggregates, same as defect_type_id)
ALTER TABLE lesiv.entity_property ADD COLUMN inspection_schedule_id INTEGER;

ALTER TABLE lesiv.entity_property RENAME COLUMN equipment_id TO entity_id;

ALTER TABLE lesiv.entity_property ADD COLUMN entity_type lesiv.entity_type;
-- Every pre-existing row described equipment - that is all the table could hold until now.
UPDATE lesiv.entity_property SET entity_type = 'equipment';
ALTER TABLE lesiv.entity_property ALTER COLUMN entity_type SET NOT NULL;

COMMENT ON TABLE lesiv.entity_property IS
    'Attributes of a plant/facility/equipment editable without holding the plant claim. One row per entity at most.';

COMMENT ON COLUMN lesiv.entity_property.entity_id IS
    'Plant, facility or equipment this row describes (see entity_type). Also the primary key - the relation is 1:1.';

COMMENT ON COLUMN lesiv.entity_property.entity_type IS
    'Kind of entity that entity_id refers to. The id alone is not self-describing: there is no FK between aggregates.';

COMMENT ON COLUMN lesiv.entity_property.inspection_schedule_id IS
    'Reference to the inspection_schedule dictionary that drives when this entity is next due for inspection. NULL when not scheduled.';
