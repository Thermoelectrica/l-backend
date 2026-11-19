-- IESK plants and simplified IESK inspections (task #72). Design: docs/iesk/backend-plan.md.
--
-- iesk_plant           - marks a plant as an IESK plant. Part of the Plant aggregate (FK to plant is allowed).
--                        Managed by hand-written SQL (docs/iesk/verification/mark_iesk_plant.sql), the app only
--                        reads it. Exposed to clients as plant.external_plant_type = 'iesk'. No triggers.
-- iesk_inspection      - simplified inspection aggregate root: one record = the only "step".
-- iesk_image           - links between an IESK inspection and images (image aggregate, no FK),
--                        analogous to inspection_image_link.

-- ============================================================================
-- Plant extension: IESK marker
-- ============================================================================

-- 1:1 extension of plant, so the PK is plant_id (not id) - same exception as for many-to-many tables.
CREATE TABLE lesiv.iesk_plant (
    plant_id UUID PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_iesk_plant_plant
        FOREIGN KEY (plant_id) REFERENCES lesiv.plant(id)
);

COMMENT ON TABLE lesiv.iesk_plant IS
    'Plants that use the simplified IESK inspection procedure. Exposed to clients as plant.external_plant_type = ''iesk''.';

-- ============================================================================
-- IESK Inspection Aggregate
-- ============================================================================

CREATE TABLE lesiv.iesk_inspection (
    id UUID PRIMARY KEY,
    equipment_id UUID NOT NULL,  -- Reference to equipment (no FK between aggregates)
    inspector_id INTEGER NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ,
    -- Same enum and lifecycle as lesiv.inspection
    status lesiv.inspection_status NOT NULL DEFAULT 'PLANNED',
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
CREATE INDEX idx_iesk_inspection_status ON lesiv.iesk_inspection(status);
CREATE INDEX idx_iesk_inspection_server_modified_at ON lesiv.iesk_inspection(server_modified_at);

-- Link table (child of iesk_inspection). Logical deletion like inspection_image_link.
CREATE TABLE lesiv.iesk_image (
    iesk_inspection_id UUID NOT NULL,
    image_id UUID NOT NULL,  -- Reference to image (no FK between aggregates)
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY (iesk_inspection_id, image_id),
    CONSTRAINT fk_iesk_image_iesk_inspection
        FOREIGN KEY (iesk_inspection_id) REFERENCES lesiv.iesk_inspection(id)
);

CREATE INDEX idx_iesk_image_image ON lesiv.iesk_image(image_id);
