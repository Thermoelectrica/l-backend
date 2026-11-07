-- ============================================================================
-- Inspection Schedule Aggregate (read-only reference data)
-- ============================================================================

CREATE TABLE lesiv.inspection_schedule (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    default_interval INTEGER NOT NULL,
    severity1_interval INTEGER NOT NULL,
    severity2_interval INTEGER NOT NULL,
    severity3_interval INTEGER NOT NULL,
    alert_interval INTEGER NOT NULL,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    server_modified_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);