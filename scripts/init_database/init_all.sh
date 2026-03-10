#!/bin/bash
# Database initialization script
# This script runs all SQL initialization files in the correct order

set -e

DB_NAME="${POSTGRES_DB:-ai_conversations}"
DB_USER="${POSTGRES_USER:-myapp_user}"
DB_PASSWORD="${POSTGRES_PASSWORD:-secure_password_123}"
DB_HOST="${POSTGRES_HOST:-localhost}"
DB_PORT="${POSTGRES_PORT:-5432}"

export PGPASSWORD="$DB_PASSWORD"

echo "Initializing database: $DB_NAME on $DB_HOST:$DB_PORT"

# Wait for PostgreSQL to be ready
until psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d postgres -c '\q' 2>/dev/null; do
  echo "Waiting for PostgreSQL to be ready..."
  sleep 2
done

echo "PostgreSQL is ready!"

# Create database if it doesn't exist
psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d postgres <<EOF
SELECT 'CREATE DATABASE $DB_NAME'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '$DB_NAME')\gexec
EOF

# Grant privileges
psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d postgres <<EOF
GRANT ALL PRIVILEGES ON DATABASE $DB_NAME TO $DB_USER;
EOF

# Run initialization scripts in order
echo "Running database initialization scripts..."

# 1. Create conversation store tables
echo "Creating conversation store tables..."
psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -f /docker-entrypoint-initdb.d/create_conv_store.sql

# 2. Create prompt configuration tables
echo "Creating prompt configuration tables..."
psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -f /docker-entrypoint-initdb.d/create_prompt_config.sql

echo "Database initialization complete!"


