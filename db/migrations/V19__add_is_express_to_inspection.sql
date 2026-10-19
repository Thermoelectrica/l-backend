-- Marks an inspection carried out by the express procedure rather than the full one.
--
-- DEFAULT FALSE is deliberate on two counts: every inspection that exists today was done by the
-- full procedure, and mobile clients that predate this field omit it from the sync PUT body.
-- An omission must therefore land on "full" - the conservative reading, and the one that keeps
-- existing reporting unchanged.

ALTER TABLE lesiv.inspection
    ADD COLUMN is_express BOOLEAN NOT NULL DEFAULT FALSE;

COMMENT ON COLUMN lesiv.inspection.is_express IS
    'Inspection was carried out by the express procedure rather than the full one. Set by the mobile app during sync.';
