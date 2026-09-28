-- Identifier of a physical tag attached to the equipment, set by the mobile app when the
-- field engineer scans the tag. Initially an NFC tag serial (UID), but deliberately named
-- after the role rather than the technology: the payload may change (different tag tech, or
-- something other than a bare serial) and the column should survive that without a rename,
-- since the field name is on the wire in the PUT body.
--
-- Nullable with no unique constraint, mirroring the existing qr_code column. A unique index
-- would turn a duplicate tag into an HTTP 400 on a mobile sync PUT; that is not wanted while
-- the semantics are still provisional and can be added in a later migration.

ALTER TABLE lesiv.equipment
    ADD COLUMN tag_code TEXT;

COMMENT ON COLUMN lesiv.equipment.tag_code IS
    'Identifier of a physical tag attached to the equipment (currently the NFC tag serial). Set by the mobile app during sync. Technology-neutral by design.';
