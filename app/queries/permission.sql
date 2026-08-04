-- Permission-related SQL queries

-- name: check_plant_access(inspector_id, plant_id)^
-- Check if inspector has access to a specific plant
SELECT EXISTS(
    SELECT 1 FROM lesiv.inspector_plant_access
    WHERE inspector_id = :inspector_id AND plant_id = :plant_id
) as has_access;

-- name: get_accessible_plants(inspector_id)
-- Get all plant IDs accessible to an inspector
SELECT plant_id
FROM lesiv.inspector_plant_access
WHERE inspector_id = :inspector_id;

-- name: get_plant_from_equipment(equipment_id)^
-- Get plant_id from equipment_id
SELECT f.plant_id
FROM lesiv.equipment e
JOIN lesiv.facility f ON e.facility_id = f.id
WHERE e.id = :equipment_id;

-- name: get_plant_from_inspection(inspection_id)^
-- Get plant_id from inspection_id
SELECT f.plant_id
FROM lesiv.inspection i
JOIN lesiv.equipment e ON i.equipment_id = e.id
JOIN lesiv.facility f ON e.facility_id = f.id
WHERE i.id = :inspection_id;

-- name: get_plant_from_defect(defect_id)^
-- Get plant_id from defect_id
SELECT f.plant_id
FROM lesiv.equipment_defect d
JOIN lesiv.equipment e ON d.equipment_id = e.id
JOIN lesiv.facility f ON e.facility_id = f.id
WHERE d.id = :defect_id;

-- name: get_plant_from_image(image_id)^
-- Get plant_id from image_id
SELECT plant_id
FROM lesiv.image
WHERE id = :image_id;

-- name: get_plant_from_work_log(work_log_id)^
-- Get plant_id from work_log_id
SELECT plant_id
FROM lesiv.work_log
WHERE id = :work_log_id;

-- name: grant_plant_access(inspector_id, plant_id)!
-- Grant plant access to an inspector
INSERT INTO lesiv.inspector_plant_access (inspector_id, plant_id)
VALUES (:inspector_id, :plant_id)
ON CONFLICT (inspector_id, plant_id) DO NOTHING;

