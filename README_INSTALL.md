# Installation Guide

This guide explains how to install and run the LangChain Agent application using Docker.

## Prerequisites

- Docker (version 20.10 or later)
- Docker Compose (version 2.0 or later, or use `docker compose` command)

## Quick Start

1. **Run the installation script:**
   ```bash
   ./scripts/shell_scripts/install.sh
   ```

   This script will:
   - Check for required tools (Docker, docker-compose)
   - Create a `.env` file with default configuration
   - Build Docker images (or use pre-loaded images)
   - Start all services (PostgreSQL, Backend API, Nginx)

2. **Access the application:**
   - Frontend: http://localhost (or http://localhost:80)
   - Backend API: http://localhost:8500
   - Database: localhost:5432

## Installation for China / Offline Use

If Docker Hub is slow or inaccessible in your region:

### Option 1: Use Chinese Docker Mirrors

Configure Docker to use Chinese registry mirrors:

```bash
sudo tee /etc/docker/daemon.json <<EOF
{
  "registry-mirrors": [
    "https://registry.docker-cn.com",
    "https://mirror.ccsogou.com",
    "https://docker.1ms.run"
  ]
}
EOF
sudo systemctl daemon-reload
sudo systemctl restart docker
```

Then run `./scripts/shell_scripts/install.sh`

### Option 2: Pre-load Docker Images Offline

1. On a machine with good Docker Hub access, run:
   ```bash
   ./scripts/shell_scripts/download_images.sh
   ```
   This creates `images.tar` with all required images.

2. Transfer `images.tar` to your target machine.

3. Load the images:
   ```bash
   docker load < images.tar
   ```

4. Run the install script:
   ```bash
   ./scripts/shell_scripts/install.sh
   ```

## Manual Installation

If you prefer to set up manually:

1. **Create environment file:**
   ```bash
   cp .env.example .env  # Edit as needed
   ```

2. **Build and start services:**
   ```bash
   cd docker
   docker compose -f docker-compose.prod.yml up -d --build
   ```

3. **Check service status:**
   ```bash
   cd docker
   docker compose -f docker-compose.prod.yml ps
   ```

## Configuration

Edit the `.env` file to customize:

- `POSTGRES_DB`: Database name (default: `ai_conversations`)
- `POSTGRES_USER`: Database user (default: `myapp_user`)
- `POSTGRES_PASSWORD`: Database password (default: `secure_password_123`)
- `POSTGRES_PORT`: PostgreSQL port (default: `5432`)
- `BACKEND_PORT`: Backend API port (default: `8500`)
- `FRONTEND_PORT`: Frontend web server port (default: `80`)

## Database Initialization

The database is automatically initialized when the PostgreSQL container starts for the first time. The following SQL scripts are executed in order:

1. `scripts/init_database/00_init_user.sh` - Creates database user and database
2. `scripts/init_database/create_conv_store.sql` - Creates conversation storage tables
3. `scripts/init_database/create_prompt_config.sql` - Creates prompt configuration tables

## Service Management

All commands run from the `docker/` directory:

### View logs:
```bash
cd docker
docker compose -f docker-compose.prod.yml logs -f

# Specific service
docker compose -f docker-compose.prod.yml logs -f backend
docker compose -f docker-compose.prod.yml logs -f postgres
docker compose -f docker-compose.prod.yml logs -f nginx
```

### Stop services:
```bash
cd docker
docker compose -f docker-compose.prod.yml down
```

### Restart services:
```bash
cd docker
docker compose -f docker-compose.prod.yml restart
```

### Rebuild after code changes:
```bash
cd docker
docker compose -f docker-compose.prod.yml up -d --build
```

### Reset database (delete all data):
```bash
cd docker
docker compose -f docker-compose.prod.yml down -v
docker compose -f docker-compose.prod.yml up -d
```

## Architecture

The application consists of three main services:

1. **PostgreSQL** (`postgres`): Database server
   - Stores conversations and prompt configurations
   - Automatically initializes schema on first run

2. **Backend** (`backend`): FastAPI application
   - Serves API endpoints at port 8500
   - Handles agent management and chat endpoints
   - Connects to PostgreSQL database

3. **Nginx** (`nginx`): Web server
   - Serves the React frontend (port 80)
   - Proxies API requests to the backend
   - Handles static file serving

## Project Structure

```
langchain-agent/
├── docker/
│   ├── docker-compose.prod.yml   # Production compose file
│   └── Dockerfile.prod           # Backend Docker image
├── scripts/
│   ├── shell_scripts/
│   │   ├── install.sh            # Main installation script
│   │   └── download_images.sh    # For offline image download
│   └── init_database/            # Database initialization scripts
├── frontend/                     # React frontend
├── configs/                      # Pipeline configurations
├── nginx.conf                    # Nginx configuration
└── .env                         # Environment variables
```

## Troubleshooting

### Database connection issues

If the backend can't connect to the database:

1. Check that PostgreSQL is running:
   ```bash
   docker compose -f docker-compose.prod.yml ps postgres
   ```

2. Verify the connection string in `.env` matches the database configuration

3. Check backend logs:
   ```bash
   docker compose -f docker-compose.prod.yml logs backend
   ```

### Frontend not loading / NetworkError

1. Check nginx logs:
   ```bash
   docker compose -f docker-compose.prod.yml logs nginx
   ```

2. Ensure frontend is built with correct API base URL. The `frontend/.env` file should contain:
   ```
   VITE_FRONT_API_BASE_URL=/
   ```
   Then rebuild: `docker compose -f docker-compose.prod.yml build backend`

### Port conflicts

If ports are already in use, update the port mappings in `.env`:

```bash
# Example: use port 5433 for PostgreSQL
POSTGRES_PORT=5433
```

## Development

For development, you may want to run services separately:

1. Start only PostgreSQL:
   ```bash
   cd docker
   docker compose -f docker-compose.prod.yml up -d postgres
   ```

2. Run backend locally:
   ```bash
   export CONN_STR="postgresql://myapp_user:secure_password_123@localhost:5432/ai_conversations"
   python -m uvicorn lang_agent.fastapi_server.combined:app --reload --host 0.0.0.0 --port 8500
   ```

3. Run frontend locally:
   ```bash
   cd frontend
   npm install
   npm run dev
   ```

Note: For local frontend development, create a `.env` file in `frontend/` with:
   ```
   VITE_FRONT_API_BASE_URL=http://localhost:8500
   ```


