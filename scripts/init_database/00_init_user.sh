#!/bin/bash
# Initialize database user and database
# This script runs before SQL files in docker-entrypoint-initdb.d
# It must be named with 00_ prefix to run first

set -e

APP_DB_NAME="${APP_DB_NAME:-ai_conversations}"
APP_DB_USER="${APP_DB_USER:-myapp_user}"
APP_DB_PASSWORD="${APP_DB_PASSWORD:-secure_password_123}"

echo "Creating database user: $APP_DB_USER"
# Create user
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    DO \$\$
    BEGIN
        IF NOT EXISTS (SELECT FROM pg_catalog.pg_user WHERE usename = '$APP_DB_USER') THEN
            CREATE USER $APP_DB_USER WITH PASSWORD '$APP_DB_PASSWORD';
        END IF;
    END
    \$\$;
    ALTER USER $APP_DB_USER CREATEDB;
EOSQL

echo "Creating database: $APP_DB_NAME"
# Create database
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    SELECT 'CREATE DATABASE $APP_DB_NAME'
    WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '$APP_DB_NAME')\gexec
    GRANT ALL PRIVILEGES ON DATABASE $APP_DB_NAME TO $APP_DB_USER;
EOSQL

echo "Granting schema privileges"
# Grant schema privileges
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$APP_DB_NAME" <<-EOSQL
    GRANT ALL ON SCHEMA public TO $APP_DB_USER;
EOSQL

echo "Database initialization complete!"

