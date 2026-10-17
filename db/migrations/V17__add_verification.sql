-- Add verification feature: enums, tables, and indexes

-- ============================================================================
-- Enums
-- ============================================================================

CREATE TYPE lesiv.verification_status AS ENUM ('SUBMITTED', 'APPROVED', 'REJECTED');
CREATE TYPE lesiv.verification_event_type AS ENUM ('SUBMITTED', 'APPROVED', 'REJECTED', 'REASSIGNED');

-- ============================================================================
-- New columns on inspection_step (server-managed, read-only from client)
-- ============================================================================

ALTER TABLE lesiv.inspection_step ADD COLUMN verified_by INTEGER;
ALTER TABLE lesiv.inspection_step ADD COLUMN verified_at TIMESTAMPTZ;

-- ============================================================================
-- Verification Aggregate
-- ============================================================================

CREATE TABLE lesiv.verification (
    id UUID PRIMARY KEY,
    inspection_step_id UUID NOT NULL,
    plant_id UUID NOT NULL,
    inspector_id INTEGER NOT NULL,
    verifier_id INTEGER NOT NULL,
    status lesiv.verification_status NOT NULL,
    server_modified_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    -- Copied fields from InspectionStep
    step_type lesiv.inspection_step_type NOT NULL,
    defect_id UUID,
    unit_name TEXT,
    description TEXT,
    is_resolved BOOLEAN,
    sticker_type_id INTEGER,
    t_sticker TEXT,
    t_environment DECIMAL(5,1),
    t_similar_unit DECIMAL(5,1),
    epsilon DECIMAL(3,2) NOT NULL DEFAULT 0.95,
    t_observed DECIMAL(5,1),
    measured_current INTEGER,
    nominal_current INTEGER,
    defect_type_id INTEGER,
    is_sticker_present BOOLEAN,
    is_test_ready BOOLEAN,
    is_attention_required BOOLEAN NOT NULL DEFAULT FALSE,
    CONSTRAINT chk_verification_t_environment_range CHECK (t_environment IS NULL OR (t_environment >= -273.15 AND t_environment <= 9999.9)),
    CONSTRAINT chk_verification_t_similar_unit_range CHECK (t_similar_unit IS NULL OR (t_similar_unit >= -273.15 AND t_similar_unit <= 9999.9)),
    CONSTRAINT chk_verification_epsilon_range CHECK (epsilon >= 0 AND epsilon <= 1)
);

CREATE INDEX idx_verification_inspection_step ON lesiv.verification(inspection_step_id);
CREATE INDEX idx_verification_plant ON lesiv.verification(plant_id);
CREATE INDEX idx_verification_inspector ON lesiv.verification(inspector_id);
CREATE INDEX idx_verification_verifier ON lesiv.verification(verifier_id);
CREATE INDEX idx_verification_status ON lesiv.verification(status);
CREATE INDEX idx_verification_server_modified_at ON lesiv.verification(server_modified_at);

-- ============================================================================
-- Verification Image Link (child entity)
-- ============================================================================

CREATE TABLE lesiv.verification_image_link (
    verification_id UUID NOT NULL,
    image_id UUID NOT NULL,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY (verification_id, image_id),
    CONSTRAINT fk_verification_image_link_verification
        FOREIGN KEY (verification_id) REFERENCES lesiv.verification(id)
);

CREATE INDEX idx_verification_image_link_verification ON lesiv.verification_image_link(verification_id);

-- ============================================================================
-- Verification Event (append-only log, not part of aggregate sync)
-- ============================================================================

CREATE TABLE lesiv.verification_event (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    verification_id UUID NOT NULL,
    event_type lesiv.verification_event_type NOT NULL,
    inspector_id INTEGER NOT NULL,
    comment TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_verification_event_verification
        FOREIGN KEY (verification_id) REFERENCES lesiv.verification(id)
);

CREATE INDEX idx_verification_event_verification ON lesiv.verification_event(verification_id);
CREATE INDEX idx_verification_event_created_at ON lesiv.verification_event(created_at);
