-- name: get_all_stickers(modified_since)
-- Get all stickers (without password_hash for security)
-- :modified_since defaults to 1790-01-01 - only return inspectors modified after that timestamp
SELECT 
    id,
    control_point_id,
    inspector_id,
    kind,
    sticker_type_id,
    sticker_color,
    from_sticker_type_id,
    count,
    installed_at,
    server_modified_at
FROM lesiv.sticker_installation
WHERE server_modified_at > :modified_since
-- WHERE kind = 'INSTALLATION';
-- WHERE sticker_color = 'YELLOW';
ORDER BY installed_at DESC;

-- name: upsert_sticker(id, control_point_id, inspector_id, kind, sticker_type_id, sticker_color, from_sticker_type_id, count, installed_at)!
-- Insert sticker
INSERT INTO lesiv.sticker_installation (
    id, control_point_id, inspector_id, kind, sticker_type_id, 
    sticker_color, from_sticker_type_id, count, installed_at
) VALUES (
    :id, :control_point_id, :inspector_id, :kind, :sticker_type_id,
    :sticker_color, :from_sticker_type_id, :count, :installed_at
)
ON CONFLICT (id) DO NOTHING;

-- name: get_by_id(id)^
-- Get sticker by ID
SELECT 
    id,
    control_point_id,
    inspector_id,
    kind,
    sticker_type_id,
    sticker_color,
    from_sticker_type_id,
    count,
    installed_at,
    server_modified_at
FROM lesiv.sticker_installation
WHERE id = :id;

-- name: get_by_plant_id(plant_id, modified_since)
-- Get all stickers for plant (full data for aggregates)
-- :modified_since defaults to 1790-01-01 - only return inspections modified after that timestamp
SELECT 
    si.id,
    si.control_point_id,
    si.inspector_id,
    si.kind,
    si.sticker_type_id,
    si.sticker_color,
    si.from_sticker_type_id,
    si.count,
    si.installed_at,
    si.server_modified_at
FROM lesiv.sticker_installation si
JOIN lesiv.inspector_plant_access ipa ON si.inspector_id = ipa.inspector_id
WHERE ipa.plant_id = :plant_id
  AND si.server_modified_at > :modified_since
ORDER BY si.server_modified_at;