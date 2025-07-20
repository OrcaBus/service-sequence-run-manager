-- Create the sequence_run_manager role
CREATE ROLE sequence_run_manager WITH LOGIN;

-- Create the sequence_run_manager database if it doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_database WHERE datname = 'sequence_run_manager') THEN
        CREATE DATABASE sequence_run_manager OWNER sequence_run_manager;
    END IF;
END
$$;

-- Grant privileges to the sequence_run_manager role
GRANT ALL PRIVILEGES ON DATABASE sequence_run_manager TO sequence_run_manager;
