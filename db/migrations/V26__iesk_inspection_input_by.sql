-- How the IESK inspection data was entered on the device (task #72). Nullable: clients that predate the field
-- do not send it, and the value is unknown for existing rows.
-- Mirrored by app.models.iesk_inspection.IeskInputBy.
CREATE TYPE lesiv.iesk_input_by AS ENUM ('UI', 'QR', 'NFC');

ALTER TABLE lesiv.iesk_inspection ADD COLUMN input_by lesiv.iesk_input_by;
