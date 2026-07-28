-- PostgreSQL Permissions Script
-- Grants minimal required permissions to l_app_role for the lesiv schema
-- Based on queries in app/queries folder
-- The role can then be granted to any user (l_app_user, dev users, etc.)

-- Grant usage on schema
GRANT USAGE ON SCHEMA lesiv TO l_app_role;

-- Grant usage on custom types
GRANT USAGE ON TYPE lesiv.log_entity_type TO l_app_role;
GRANT USAGE ON TYPE lesiv.log_operation TO l_app_role;
GRANT USAGE ON TYPE lesiv.defect_status TO l_app_role;
GRANT USAGE ON TYPE lesiv.inspection_status TO l_app_role;
GRANT USAGE ON TYPE lesiv.inspection_step_type TO l_app_role;
GRANT USAGE ON TYPE lesiv.defect_severity TO l_app_role;
GRANT USAGE ON TYPE lesiv.image_type TO l_app_role;
GRANT USAGE ON TYPE lesiv.step_status TO l_app_role;
-- Added in V6__access_levels.sql
GRANT USAGE ON TYPE lesiv.access_level TO l_app_role;
-- Added in V8__add_upload_status_to_image.sql
GRANT USAGE ON TYPE lesiv.image_upload_status TO l_app_role;
-- Added in V11_sticker_installation.sql
GRANT USAGE ON TYPE lesiv.sticker_event_kind TO l_app_role;
GRANT USAGE ON TYPE lesiv.sticker_color  TO l_app_role;

-- ============================================================================
-- Plant permissions
-- ============================================================================

-- inspector_plant_access: SELECT
GRANT SELECT ON lesiv.inspector_plant_access TO l_app_role;

-- ============================================================================
-- Inspector Aggregate
-- ============================================================================

-- inspector: SELECT (auth queries), UPDATE (password change)
GRANT SELECT, UPDATE ON lesiv.inspector TO l_app_role;

-- tokens: SELECT, INSERT, UPDATE, DELETE (auth operations and cleanup)
GRANT SELECT, INSERT, UPDATE, DELETE ON lesiv.tokens TO l_app_role;

-- ============================================================================
-- StickerType Aggregate
-- ============================================================================

-- sticker_type: SELECT only (read-only reference data)
GRANT SELECT ON lesiv.sticker_type TO l_app_role;

-- sticker_temp_range: SELECT only (read-only reference data)
GRANT SELECT ON lesiv.sticker_temp_range TO l_app_role;

-- ============================================================================
-- Equipment Type Aggregate
-- ============================================================================

-- equipment_type: SELECT only (read-only reference data)
GRANT SELECT ON lesiv.equipment_type TO l_app_role;

-- equipment_control_point_template: SELECT only (read-only reference data)
GRANT SELECT ON lesiv.equipment_control_point_template TO l_app_role;

-- ============================================================================
-- Defect Type Aggregate
-- ============================================================================

-- defect_type: SELECT only (read-only reference data)
GRANT SELECT ON lesiv.defect_type TO l_app_role;

-- ============================================================================
-- Facility Template Aggregate
-- ============================================================================

-- facility_template: SELECT only (read-only reference data)
GRANT SELECT ON lesiv.facility_template TO l_app_role;

-- facility_template_equipment: SELECT only (read-only reference data)
GRANT SELECT ON lesiv.facility_template_equipment TO l_app_role;

-- ============================================================================
-- Log
-- ============================================================================

-- log: INSERT only (write-only audit log)
GRANT INSERT ON lesiv.log TO l_app_role;

-- Grant usage on log.id sequence for INSERT operations
GRANT USAGE ON SEQUENCE lesiv.log_id_seq TO l_app_role;

-- ============================================================================
-- Plant Aggregate
-- ============================================================================

-- plant: SELECT, INSERT, UPDATE 
GRANT SELECT, INSERT, UPDATE ON lesiv.plant TO l_app_role;

-- facility: SELECT, INSERT, UPDATE 
GRANT SELECT, INSERT, UPDATE ON lesiv.facility TO l_app_role;

-- ============================================================================
-- Equipment Aggregate
-- ============================================================================

-- equipment: SELECT, INSERT, UPDATE 
GRANT SELECT, INSERT, UPDATE ON lesiv.equipment TO l_app_role;

-- equipment_control_point: SELECT, INSERT, UPDATE 
GRANT SELECT, INSERT, UPDATE ON lesiv.equipment_control_point TO l_app_role;

-- equipment_defect: SELECT, INSERT, UPDATE 
GRANT SELECT, INSERT, UPDATE ON lesiv.equipment_defect TO l_app_role;

-- ============================================================================
-- Inspection Aggregate
-- ============================================================================

-- inspection: SELECT, INSERT, UPDATE 
GRANT SELECT, INSERT, UPDATE ON lesiv.inspection TO l_app_role;

-- inspection_step: SELECT, INSERT, UPDATE 
GRANT SELECT, INSERT, UPDATE ON lesiv.inspection_step TO l_app_role;

-- inspection_image_link: SELECT, INSERT, UPDATE 
GRANT SELECT, INSERT, UPDATE ON lesiv.inspection_image_link TO l_app_role;

-- ============================================================================
-- Image Aggregate
-- ============================================================================

-- image: SELECT, INSERT, UPDATE, DELETE (full CRUD including hard delete)
GRANT SELECT, INSERT, UPDATE, DELETE ON lesiv.image TO l_app_role;

-- ============================================================================
-- Work Log aggregate
-- ============================================================================

-- image: SELECT, INSERT, UPDATE, DELETE (full CRUD including hard delete)
GRANT SELECT, INSERT, UPDATE, DELETE ON lesiv.work_log TO l_app_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON lesiv.work_log_inspector TO l_app_role;

-- ============================================================================
-- Sticker Installation Aggregate
-- ============================================================================

-- plant_group: SELECT, INSERT, UPDATE
GRANT SELECT, INSERT, UPDATE ON lesiv.sticker_installation TO l_app_role;


-- ============================================================================
-- Plant Group Aggregate
-- ============================================================================

-- plant_group: SELECT, INSERT, UPDATE
GRANT SELECT, INSERT, UPDATE ON lesiv.plant_group TO l_app_role;

-- ============================================================================
-- Views
-- ============================================================================

-- equipment_detailed_view: SELECT (read-only aggregated view, created in R__equipment_detailed_view.sql)
GRANT SELECT ON lesiv.equipment_detailed_view TO l_app_role;

-- ============================================================================
-- Functions
-- ============================================================================

-- create_inspector: used by admin scripts to create inspectors with hashed passwords
GRANT EXECUTE ON FUNCTION lesiv.create_inspector
(TEXT, TEXT, TEXT, lesiv.access_level, BOOLEAN) TO l_app_role;

-- change_password: called by the app for password change operations
GRANT EXECUTE ON FUNCTION lesiv.change_password
(TEXT, TEXT) TO l_app_role;

-- ============================================================================
-- Sequences
-- ============================================================================

-- Grant usage on sequences for SERIAL columns that need INSERT
GRANT USAGE ON SEQUENCE lesiv.inspector_id_seq TO l_app_role;
GRANT USAGE ON SEQUENCE lesiv.sticker_type_id_seq TO l_app_role;
GRANT USAGE ON SEQUENCE lesiv.sticker_temp_range_id_seq TO l_app_role;
GRANT USAGE ON SEQUENCE lesiv.equipment_type_id_seq TO l_app_role;
GRANT USAGE ON SEQUENCE lesiv.equipment_control_point_template_id_seq TO l_app_role;

-- Note: UUID-based tables (plant, facility, equipment, equipment_defect, 
-- inspection, inspection_step, image, tokens) don't need sequence permissions
