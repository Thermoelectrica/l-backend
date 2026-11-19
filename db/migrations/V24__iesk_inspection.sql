-- Plant extensions and simplified IESK inspections (task #72). API contract: docs/iesk/api-contract.md.
--
-- plant_extension      - feature flags of a plant: a row (plant_id, extension_type) enables the extension.
--                        Part of the Plant aggregate (FK to plant is allowed). Managed by hand-written SQL,
--                        the app only reads it. Exposed to clients as plant.extensions = ["IESK", ...].
--                        No triggers.
-- iesk_inspection      - simplified inspection aggregate root: one record = the only "step".
-- iesk_inspection_image_link - links between an IESK inspection and images (image aggregate, no FK),
--                        analogous to inspection_image_link.

-- ============================================================================
-- Plant extensions
-- ============================================================================

-- Mirrored by app.models.plant.PlantExtensionType. A new value needs its own migration
-- (ALTER TYPE ... ADD VALUE cannot be used in the transaction that adds it) and a new enum member.
CREATE TYPE lesiv.plant_extension_type AS ENUM (
    'IESK'  -- simplified IESK inspections (/iesk-inspection)
);

-- Flag table: both columns form the PK, so there is no id (same exception as for many-to-many tables).
CREATE TABLE lesiv.plant_extension (
    plant_id UUID NOT NULL,
    extension_type lesiv.plant_extension_type NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (plant_id, extension_type),
    CONSTRAINT fk_plant_extension_plant
        FOREIGN KEY (plant_id) REFERENCES lesiv.plant(id)
);

COMMENT ON TABLE lesiv.plant_extension IS
    'Extensions enabled for a plant (feature flags). Exposed to clients as plant.extensions.';

-- ============================================================================
-- IESK Inspection Aggregate
-- ============================================================================

CREATE TABLE lesiv.iesk_inspection (
    id UUID PRIMARY KEY,
    equipment_id UUID NOT NULL,  -- Reference to equipment (no FK between aggregates)
    inspector_id INTEGER NOT NULL,
    -- When the inspection was created on the device (set by the client, offline-first).
    -- Written on insert only, later PUTs do not change it.
    created_at TIMESTAMPTZ NOT NULL,
    -- Checklist marks. Nullable: an inspection is created on the device before it is filled in.
    oil_level INTEGER,
    bugs INTEGER,
    dimensions INTEGER,
    locks INTEGER,
    stickers INTEGER,
    comment TEXT,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    server_modified_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_iesk_inspection_inspector
        FOREIGN KEY (inspector_id) REFERENCES lesiv.inspector(id)
);

CREATE INDEX idx_iesk_inspection_equipment ON lesiv.iesk_inspection(equipment_id);
CREATE INDEX idx_iesk_inspection_inspector ON lesiv.iesk_inspection(inspector_id);
CREATE INDEX idx_iesk_inspection_server_modified_at ON lesiv.iesk_inspection(server_modified_at);

-- Link table (child of iesk_inspection), same layout as inspection_image_link. Logical deletion.
CREATE TABLE lesiv.iesk_inspection_image_link (
    image_id UUID NOT NULL,  -- Reference to image (no FK between aggregates)
    iesk_inspection_id UUID NOT NULL,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY (image_id, iesk_inspection_id),
    CONSTRAINT fk_iesk_inspection_image_link_iesk_inspection
        FOREIGN KEY (iesk_inspection_id) REFERENCES lesiv.iesk_inspection(id)
);

CREATE INDEX idx_iesk_inspection_image_link_iesk_inspection
    ON lesiv.iesk_inspection_image_link(iesk_inspection_id);
