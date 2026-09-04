-- Create a comprehensive view for equipment with all related information
-- This view includes:
-- 1) All fields from equipment
-- 2) Path to the equipment using parent_id (hierarchical path)
-- 3) Facility name
-- 4) Plant name and id
-- 5) Last inspection date and inspector full name
-- 6) Sum of control point and sticker count
-- 7) Number of active and resolved defects

CREATE OR REPLACE VIEW lesiv.equipment_detailed_view AS
WITH RECURSIVE equipment_path AS (
    -- Base case: equipment without parent
    SELECT 
        e.id,
        e.name::TEXT AS path,
        1 AS depth
    FROM lesiv.equipment e
    WHERE e.parent_id IS NULL
    
    UNION ALL
    
    -- Recursive case: equipment with parent
    SELECT 
        e.id,
        ep.path || ' > ' || e.name AS path,
        ep.depth + 1 AS depth
    FROM lesiv.equipment e
    INNER JOIN equipment_path ep ON e.parent_id = ep.id
),
last_inspection AS (
    -- Get the most recent inspection for each equipment
    SELECT DISTINCT ON (i.equipment_id)
        i.equipment_id,
        i.started_at AS last_inspection_date,
        insp.full_name AS last_inspector_name
    FROM lesiv.inspection i
    INNER JOIN lesiv.inspector insp ON i.inspector_id = insp.id
    WHERE i.is_deleted = FALSE
    ORDER BY i.equipment_id, i.started_at DESC
),
control_point_summary AS (
    -- Sum control points and stickers for each equipment
    SELECT 
        ecp.equipment_id,
        COALESCE(SUM(ecp.point_count), 0) AS total_point_count,
        COALESCE(SUM(si.count), 0) AS total_sticker_count
    FROM lesiv.equipment_control_point ecp
    JOIN lesiv.sticker_installation si on ecp.id = si.control_point_id
    WHERE ecp.is_deleted = FALSE
    GROUP BY ecp.equipment_id
),
defect_summary AS (
    -- Count active and resolved defects for each equipment
    SELECT 
        ed.equipment_id,
        COUNT(*) FILTER (WHERE ed.status = 'DETECTED') AS active_defect_count,
        COUNT(*) FILTER (WHERE ed.status = 'RESOLVED') AS resolved_defect_count
    FROM lesiv.equipment_defect ed
    WHERE ed.is_deleted = FALSE
    GROUP BY ed.equipment_id
)
SELECT 
    -- All fields from equipment
    e.id,
    e.facility_id,
    e.parent_id,
    e.name,
    e.qr_code,
    e.is_container,
    e.equipment_type_id,
    e.facility_template_equipment_id,
    e.estimated_point_count,
    e.is_deleted,
    e.server_modified_at,
    
    -- Equipment path
    COALESCE(ep.path, e.name) AS equipment_path,
    COALESCE(ep.depth, 1) AS equipment_depth,
    
    -- Facility information
    f.name AS facility_name,
    f.facility_template_id,
    
    -- Plant information
    p.id AS plant_id,
    p.name AS plant_name,
    
    -- Equipment type information
    et.name AS equipment_type_name,
    
    -- Last inspection information
    li.last_inspection_date,
    li.last_inspector_name,
    
    -- Control point and sticker summary
    COALESCE(cps.total_point_count, 0) AS total_point_count,
    COALESCE(cps.total_sticker_count, 0) AS total_sticker_count,
    
    -- Defect summary
    COALESCE(ds.active_defect_count, 0) AS active_defect_count,
    COALESCE(ds.resolved_defect_count, 0) AS resolved_defect_count,
    COALESCE(ds.active_defect_count, 0) + COALESCE(ds.resolved_defect_count, 0) AS total_defect_count
    
FROM lesiv.equipment e
LEFT JOIN equipment_path ep ON e.id = ep.id
INNER JOIN lesiv.facility f ON e.facility_id = f.id
INNER JOIN lesiv.plant p ON f.plant_id = p.id
LEFT JOIN lesiv.equipment_type et ON e.equipment_type_id = et.id
LEFT JOIN last_inspection li ON e.id = li.equipment_id
LEFT JOIN control_point_summary cps ON e.id = cps.equipment_id
LEFT JOIN defect_summary ds ON e.id = ds.equipment_id;

-- Create an index on the underlying equipment table for better view performance
-- (if not already exists from previous migrations)
CREATE INDEX IF NOT EXISTS idx_equipment_facility_id ON lesiv.equipment(facility_id);

-- Add comment to the view
COMMENT ON VIEW lesiv.equipment_detailed_view IS 
'Comprehensive view of equipment with hierarchical path, facility/plant information, inspection history, control points, and defect counts';
