-- Create the sequence_run_manager role (if it doesn't exist)
-- Note: The database is already created by PostgreSQL due to POSTGRES_DB environment variable
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'sequence_run_manager') THEN
        CREATE ROLE sequence_run_manager WITH LOGIN;
    END IF;
END
$$;

-- Change database owner to sequence_run_manager
ALTER DATABASE sequence_run_manager OWNER TO sequence_run_manager;

-- Grant privileges to the sequence_run_manager role
GRANT ALL PRIVILEGES ON DATABASE sequence_run_manager TO sequence_run_manager;
