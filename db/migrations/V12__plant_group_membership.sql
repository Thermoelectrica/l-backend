-- Create plant_group_membership table.
-- Membership belongs to the plant_group aggregate (not to plant).
-- plant_id is PK to enforce 1:N constraint (each plant in at most one group).
-- No FK to plant — cross-aggregate reference per project conventions.
CREATE TABLE lesiv.plant_group_membership
(
    plant_id UUID NOT NULL,
    plant_group_id UUID NOT NULL,
    CONSTRAINT pk_plant_group_membership PRIMARY KEY (plant_id),
    CONSTRAINT fk_pgm_plant_group
        FOREIGN KEY (plant_group_id)
        REFERENCES lesiv.plant_group(id)
);

CREATE INDEX idx_pgm_plant_group_id ON lesiv.plant_group_membership(plant_group_id);

-- Remove plant_group_id column from plant table (membership now lives in plant_group aggregate)
DROP INDEX IF EXISTS lesiv.idx_plant_group;
ALTER TABLE lesiv.plant DROP COLUMN IF EXISTS plant_group_id;
