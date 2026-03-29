-- Create application database (Docker entrypoint handles this via POSTGRES_DB,
-- but we need the schema, extensions, and roles)

-- Extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Application schema
CREATE SCHEMA IF NOT EXISTS expense_tracker;

-- Application role (used at runtime, RLS applies)
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'app_user') THEN
        CREATE ROLE app_user LOGIN PASSWORD 'app_password_dev';
    END IF;
END
$$;

-- Grant schema access
GRANT USAGE, CREATE ON SCHEMA expense_tracker TO app_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA expense_tracker GRANT ALL ON TABLES TO app_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA expense_tracker GRANT ALL ON SEQUENCES TO app_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA expense_tracker GRANT EXECUTE ON FUNCTIONS TO app_user;

-- Set default search_path for app_user
ALTER ROLE app_user SET search_path TO expense_tracker, public;

-- RLS helper function
CREATE OR REPLACE FUNCTION expense_tracker.current_app_user_id()
RETURNS uuid AS $$
BEGIN
    RETURN current_setting('app.current_user_id', true)::uuid;
EXCEPTION
    WHEN OTHERS THEN
        RETURN NULL;
END;
$$ LANGUAGE plpgsql STABLE;

-- Grant execute on the function
GRANT EXECUTE ON FUNCTION expense_tracker.current_app_user_id() TO app_user;
