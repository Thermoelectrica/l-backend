-- ============================================================================
-- create_inspector: Creates a new inspector with hashed password
-- ============================================================================

-- Drop old signatures (PostgreSQL doesn't allow changing parameters in CREATE OR REPLACE:
-- a different arity creates an overload instead of replacing the function).
DROP FUNCTION IF EXISTS lesiv.create_inspector(TEXT, TEXT, TEXT);
DROP FUNCTION IF EXISTS lesiv.create_inspector(TEXT, TEXT, TEXT, lesiv.access_level, BOOLEAN);

CREATE OR REPLACE FUNCTION lesiv.create_inspector(
    p_full_name TEXT,
    p_username TEXT,
    p_password TEXT,
    p_access_level lesiv.access_level DEFAULT 'MODIFY',
    p_allow_all_plants BOOLEAN DEFAULT TRUE,
    -- Internal (company) inspector. Defaults to FALSE so a forgotten argument produces a
    -- restricted user rather than one that sees every plant we create from now on.
    p_is_internal BOOLEAN DEFAULT FALSE
)
RETURNS INTEGER
LANGUAGE plpgsql
AS $$
DECLARE
    v_inspector_id INTEGER;
BEGIN
    -- Create inspector with access level
    INSERT INTO lesiv.inspector (full_name, username, password_hash, access_level, is_internal)
    VALUES (
        p_full_name,
        p_username,
        crypt(p_password, gen_salt('bf', 12)),
        p_access_level,
        p_is_internal
    )
    RETURNING id INTO v_inspector_id;

    -- Grant access to all plants if requested.
    -- External inspectors never get the blanket grant: the whole point of is_internal is that
    -- they are limited to a predefined list of plants granted to them explicitly.
    IF p_allow_all_plants AND p_is_internal THEN
        INSERT INTO lesiv.inspector_plant_access (inspector_id, plant_id)
        SELECT v_inspector_id, id
        FROM lesiv.plant
        WHERE NOT is_deleted
        ON CONFLICT (inspector_id, plant_id) DO NOTHING;
    END IF;

    RETURN v_inspector_id;
END;
$$;
