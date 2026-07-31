CREATE TABLE lesiv.plant_group (
    id UUID PRIMARY KEY,
    name TEXT NOT NULL,
    parent_id UUID NULL,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    server_modified_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_group_parent_group 
        FOREIGN KEY (parent_id) 
        REFERENCES lesiv.plant_group(id)
        ON DELETE SET NULL
);

CREATE INDEX idx_group_parent_group ON lesiv.plant_group(parent_id);

ALTER TABLE lesiv.plant 
ADD COLUMN plant_group_id UUID NULL;

CREATE INDEX idx_plant_group ON lesiv.plant(plant_group_id);
