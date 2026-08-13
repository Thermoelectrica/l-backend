-- Remove unused from_sticker_type_id column from sticker_installation
ALTER TABLE lesiv.sticker_installation DROP COLUMN IF EXISTS from_sticker_type_id;
