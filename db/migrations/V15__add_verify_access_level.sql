-- Add VERIFY access level: a strict superset of MODIFY.
-- Placed AFTER 'MODIFY' so the native enum sort order matches the privilege order
-- (READ < INSPECT < MODIFY < VERIFY).
--
-- This migration must contain only the ALTER TYPE: PostgreSQL forbids using a new
-- enum value in the same transaction that added it, and Flyway wraps each migration
-- in one transaction. Any UPDATE ... = 'VERIFY' has to go in a later migration.

ALTER TYPE lesiv.access_level ADD VALUE IF NOT EXISTS 'VERIFY' AFTER 'MODIFY';

COMMENT ON TYPE lesiv.access_level IS 'Access level for inspectors: READ (GET only), INSPECT (GET + inspections/defects), MODIFY (all operations), VERIFY (MODIFY + verification)';
