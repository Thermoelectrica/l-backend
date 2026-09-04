-- Split inspectors into internal (company staff) and external (customers/contractors).
-- Only internal inspectors are auto-granted access to newly created plants; external users
-- are limited to a predefined list of plants granted to them explicitly.
--
-- DEFAULT FALSE is deliberate: inspectors are created by hand-written SQL, so the column will
-- eventually be omitted. An omission must land on the restricted side - a forgotten flag on an
-- external user would otherwise silently leak every plant we create to an outside company.

ALTER TABLE lesiv.inspector
    ADD COLUMN is_internal BOOLEAN NOT NULL DEFAULT FALSE;

-- Every inspector that exists today is company staff.
UPDATE lesiv.inspector SET is_internal = TRUE;

COMMENT ON COLUMN lesiv.inspector.is_internal IS
    'Internal (company) inspector. Only internal inspectors are auto-granted access to newly created plants. External users are limited to explicitly granted plants.';
