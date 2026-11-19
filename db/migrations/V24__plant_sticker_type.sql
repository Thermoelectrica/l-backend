-- Sticker types permitted for a specific plant.
-- An empty set of rows means that the plant permits every sticker type.
CREATE TABLE lesiv.plant_sticker_type (
    plant_id UUID NOT NULL,
    sticker_type_id INTEGER NOT NULL,
    CONSTRAINT pk_plant_sticker_type PRIMARY KEY (plant_id, sticker_type_id),
    CONSTRAINT fk_plant_sticker_type_plant
        FOREIGN KEY (plant_id) REFERENCES lesiv.plant(id),
    CONSTRAINT fk_plant_sticker_type_sticker_type
        FOREIGN KEY (sticker_type_id) REFERENCES lesiv.sticker_type(id)
);

-- The composite primary key covers all application queries by plant_id.
