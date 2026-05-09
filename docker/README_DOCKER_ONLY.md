# Docker-Only Installation (Cross-Platform)

This installation method works on **Windows, macOS, and Linux** without requiring any shell scripts or native Python/Conda installation on the host machine.

## Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop) (Windows/Mac) or Docker Engine (Linux)
- Docker Compose v2.0+
- Git (to clone this repository)

## Quick Start

### 1. Clone the Repository

```bash
git clone <repository-url>
cd langchain-agent
```

### 2. Create Environment File

Copy the example environment file and edit as needed:

**Windows (PowerShell):**
```powershell
copy .env.example .env
```

**Mac/Linux:**
```bash
cp .env.example .env
```

Or create `.env` manually with this content:
```env
# Database Configuration
POSTGRES_DB=ai_conversations
POSTGRES_USER=myapp_user
POSTGRES_PASSWORD=secure_password_123
POSTGRES_PORT=5434

# Backend Configuration
BACKEND_PORT=8500

# Frontend Configuration
FRONTEND_PORT=8080

# Database Connection String (used by backend)
CONN_STR=postgresql://myapp_user:secure_password_123@postgres:5432/ai_conversations

# API Authentication (optional)
FAST_AUTH_KEYS=your-api-key-here
```

### 3. Start All Services

**Windows/Mac/Linux (same command):**

```bash
cd docker
docker compose -f docker-compose.docker-only.yml up -d
```

That's it! The services will start in the background.

### 4. Access the Application

- **Frontend UI:** http://localhost:8080
- **Backend API:** http://localhost:8500
- **Database:** localhost:5434 (PostgreSQL)
- **RabbitMQ Management:** http://localhost:15672 (guest/guest)

### 5. View Logs

```bash
# All services
docker compose -f docker-compose.docker-only.yml logs -f

# Specific service
docker compose -f docker-compose.docker-only.yml logs -f backend
docker compose -f docker-compose.docker-only.yml logs -f postgres
```

## Managing Services

### Stop Services

```bash
docker compose -f docker-compose.docker-only.yml down
```

### Restart Services

```bash
docker compose -f docker-compose.docker-only.yml restart
```

### Rebuild After Code Changes

```bash
docker compose -f docker-compose.docker-only.yml up -d --build
```

### Reset Database (Delete All Data)

⚠️ **Warning:** This deletes all data!

```bash
docker compose -f docker-compose.docker-only.yml down -v
docker compose -f docker-compose.docker-only.yml up -d
```

## How It Works

The Docker-only setup uses a special entrypoint script (`docker/docker-entrypoint.sh`) that runs **inside the container**:

1. **Pipeline Registration:** Automatically scans `configs/pipelines/*.yaml` and registers them in `configs/pipeline_registry.json`
2. **Database Wait:** Waits for PostgreSQL to be ready before starting the backend
3. **Server Start:** Starts the combined FastAPI server

This approach ensures the initialization happens in a consistent Linux environment, regardless of your host OS.

## Customizing Pipeline Configs

The `configs/` directory is mounted as a volume, so you can:

1. Edit YAML files in `configs/pipelines/` on your host machine
2. Restart the backend: `docker compose -f docker-compose.docker-only.yml restart backend`
3. The new pipelines will be automatically registered on restart

## Troubleshooting

### Port Conflicts

If you get "port already in use" errors, edit `.env` and change the ports:

```env
POSTGRES_PORT=5435      # Instead of 5434
BACKEND_PORT=8501        # Instead of 8500
FRONTEND_PORT=8081       # Instead of 8080
```

### Slow Startup on Windows

WSL2 backend can be slow on first run. If services fail to start:

```bash
# Wait a bit longer, then restart
docker compose -f docker-compose.docker-only.yml restart
```

### Database Connection Issues

Check that all services are healthy:

```bash
docker compose -f docker-compose.docker-only.yml ps
```

View postgres logs:

```bash
docker compose -f docker-compose.docker-only.yml logs postgres
```

### Pipeline Not Showing in Frontend

1. Check that the YAML file exists in `configs/pipelines/`
2. Restart the backend: `docker compose -f docker-compose.docker-only.yml restart backend`
3. Check backend logs: `docker compose -f docker-compose.docker-only.yml logs backend | head -50`

## Comparison: Docker-Only vs. Original Install Script

| Feature | Docker-Only (This) | Original Install Script |
|---------|-------------------|-------------------------|
| **Works on Windows** | ✅ Yes (PowerShell or CMD) | ❌ No (requires Bash/WSL2) |
| **Works on macOS** | ✅ Yes | ✅ Yes |
| **Works on Linux** | ✅ Yes | ✅ Yes |
| **Requires Python on Host** | ❌ No | ✅ Yes |
| **Requires Conda on Host** | ❌ No | ✅ Yes |
| **Requires Bash on Host** | ❌ No | ✅ Yes |
| **Build Time** | ⏱️ Longer (initial build) | ⏱️ Shorter (uses host Python) |
| **Disk Usage** | 💾 Larger (containers) | 💾 Smaller (native) |
| **Isolation** | 🔒 High (containers) | 🔓 Lower (host environment) |

## For Developers: Local Python Development

If you want to develop with native Python instead of Docker:

1. Follow the main [README_INSTALL.md](../README_INSTALL.md) for Conda setup
2. Or use the original `scripts/shell_scripts/install.sh` on macOS/Linux

## Support

For issues specific to the Docker-only setup:
1. Check logs: `docker compose -f docker-compose.docker-only.yml logs`
2. Verify `.env` file exists and has correct values
3. Ensure ports are not in use by other applications
