-- Create read-only user for the agent
CREATE USER contexthub_readonly WITH PASSWORD 'contexthub';

-- Grant connect
GRANT CONNECT ON DATABASE contexthub TO contexthub_readonly;

-- Create schemas
CREATE SCHEMA IF NOT EXISTS business;
CREATE SCHEMA IF NOT EXISTS context;

-- Grant read-only access to business schema
GRANT USAGE ON SCHEMA business TO contexthub_readonly;
GRANT USAGE ON SCHEMA context TO contexthub_readonly;
ALTER DEFAULT PRIVILEGES IN SCHEMA business GRANT SELECT ON TABLES TO contexthub_readonly;
ALTER DEFAULT PRIVILEGES IN SCHEMA context GRANT SELECT ON TABLES TO contexthub_readonly;
