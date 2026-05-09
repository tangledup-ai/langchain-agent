#!/bin/bash
# Docker-only entrypoint that handles initialization
# This runs inside the container, making it cross-platform (Windows/Mac/Linux)

set -e

echo "=== LangChain Agent Docker Initialization ==="

# Step 1: Register pipelines from configs/pipelines/
echo "Registering pipeline configurations..."
cd /app
python3 scripts/py_scripts/register_pipelines.py || echo "Pipeline registration may have issues, continuing..."

# Step 2: Wait for database
echo "Waiting for database to be ready..."
python3 << EOF
import sys
import time
import psycopg
import os

max_attempts = 30
conn_str = os.environ.get("CONN_STR", "")

for i in range(max_attempts):
    try:
        with psycopg.connect(conn_str, connect_timeout=2) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
        print("Database is ready!")
        sys.exit(0)
    except Exception as e:
        if i == max_attempts - 1:
            print(f"Warning: Database not ready after {max_attempts * 2} seconds, continuing anyway...")
            print(f"Error: {e}")
            sys.exit(0)
        print(f"Database is unavailable - sleeping (attempt {i+1}/{max_attempts})")
        time.sleep(2)
EOF

# Step 3: Start the server
echo "Starting server..."
exec "$@"
