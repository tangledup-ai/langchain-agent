#!/bin/bash
# Run SQL initialization files in the correct database context
# This script runs after 00_init_user.sh creates the database

set -e

APP_DB_NAME="${APP_DB_NAME:-ai_conversations}"

echo "Running SQL initialization files in database: $APP_DB_NAME"

# Run create_conv_store.sql
if [ -f /docker-entrypoint-initdb.d/create_conv_store.sql ]; then
    echo "Executing create_conv_store.sql..."
    psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$APP_DB_NAME" -f /docker-entrypoint-initdb.d/create_conv_store.sql
fi

# Run create_prompt_config.sql
if [ -f /docker-entrypoint-initdb.d/create_prompt_config.sql ]; then
    echo "Executing create_prompt_config.sql..."
    psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$APP_DB_NAME" -f /docker-entrypoint-initdb.d/create_prompt_config.sql
fi

echo "SQL initialization files completed!"


