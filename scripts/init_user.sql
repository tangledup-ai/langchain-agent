-- Create a new database
CREATE DATABASE ai_conversations;

-- Create a dedicated user (role) for your app
CREATE USER myapp_user WITH PASSWORD 'secure_password_123';

-- Grant privileges
GRANT ALL PRIVILEGES ON DATABASE ai_conversations TO myapp_user;

-- Also needed: allow user to create schemas/tables
\c ai_conversations
ALTER USER myapp_user CREATEDB;  -- optional but helpful during dev
GRANT ALL ON SCHEMA public TO myapp_user;