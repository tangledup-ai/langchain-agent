#!/bin/bash
# Installation script for LangChain Agent
# This script sets up and runs the entire application stack

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"
ENV_FILE="$PROJECT_ROOT/.env"

echo -e "${GREEN}=== LangChain Agent Installation Script ===${NC}\n"

# Check for required tools
check_requirements() {
    echo -e "${YELLOW}Checking requirements...${NC}"
    
    if ! command -v docker &> /dev/null; then
        echo -e "${RED}Error: Docker is not installed. Please install Docker first.${NC}"
        exit 1
    fi
    
    if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
        echo -e "${RED}Error: docker-compose is not installed. Please install docker-compose first.${NC}"
        exit 1
    fi
    
    echo -e "${GREEN}✓ All requirements met${NC}\n"
}

# Create .env file if it doesn't exist
create_env_file() {
    if [ ! -f "$ENV_FILE" ]; then
        echo -e "${YELLOW}Creating .env file...${NC}"
        cat > "$ENV_FILE" <<EOF
# Database Configuration
POSTGRES_DB=ai_conversations
POSTGRES_USER=myapp_user
POSTGRES_PASSWORD=secure_password_123
POSTGRES_PORT=5432

# Backend Configuration
BACKEND_PORT=8500

# Frontend Configuration
FRONTEND_PORT=8080

# Database Connection String (used by backend)
CONN_STR=postgresql://myapp_user:secure_password_123@postgres:5432/ai_conversations
EOF
        echo -e "${GREEN}✓ Created .env file at $ENV_FILE${NC}"
        echo -e "${YELLOW}  Please review and update the .env file with your preferred settings.${NC}\n"
    else
        echo -e "${GREEN}✓ .env file already exists${NC}\n"
    fi
}

# Build Docker images
build_images() {
    echo -e "${YELLOW}Building Docker images (including frontend)...${NC}"
    cd "$PROJECT_ROOT"
    
    # Check if docker-compose or docker compose
    if docker compose version &> /dev/null; then
        COMPOSE_CMD="docker compose"
    else
        COMPOSE_CMD="docker-compose"
    fi
    
    $COMPOSE_CMD -f docker/docker-compose.prod.yml build
    
    echo -e "${GREEN}✓ Docker images built successfully${NC}\n"
}

# Initialize database
init_database() {
    echo -e "${YELLOW}Initializing database...${NC}"
    
    # Wait for PostgreSQL to be ready
    echo "Waiting for PostgreSQL to start..."
    sleep 5
    
    # The SQL files in scripts/init_database/ will be automatically executed
    # by PostgreSQL's docker-entrypoint-initdb.d mechanism
    # We just need to wait a bit for it to complete
    
    echo -e "${GREEN}✓ Database initialization will be handled automatically by PostgreSQL container${NC}\n"
}

# Start services
start_services() {
    echo -e "${YELLOW}Starting services...${NC}"
    cd "$PROJECT_ROOT"
    
    # Check if docker-compose or docker compose
    if docker compose version &> /dev/null; then
        COMPOSE_CMD="docker compose"
    else
        COMPOSE_CMD="docker-compose"
    fi
    
    $COMPOSE_CMD -f docker/docker-compose.prod.yml up -d
    
    echo -e "${GREEN}✓ Services started${NC}\n"
}

# Show status
show_status() {
    # Load environment variables from .env if it exists
    if [ -f "$ENV_FILE" ]; then
        set -a
        source "$ENV_FILE"
        set +a
    fi
    
    echo -e "${GREEN}=== Installation Complete ===${NC}\n"
    echo -e "Services are starting up. Please wait a moment for them to be ready.\n"
    echo -e "Access points:"
    echo -e "  - Frontend:     http://localhost:${FRONTEND_PORT:-80}"
    echo -e "  - Backend API:  http://localhost:${BACKEND_PORT:-8500}"
    echo -e "  - Database:     localhost:${POSTGRES_PORT:-5432}\n"
    echo -e "To view logs:"
    echo -e "  docker-compose -f docker/docker-compose.prod.yml logs -f\n"
    echo -e "To stop services:"
    echo -e "  docker-compose -f docker/docker-compose.prod.yml down\n"
    echo -e "To restart services:"
    echo -e "  docker-compose -f docker/docker-compose.prod.yml restart\n"
}

# Main execution
main() {
    check_requirements
    create_env_file
    build_images
    start_services
    init_database
    show_status
    
    echo -e "${YELLOW}Waiting for services to be healthy...${NC}"
    sleep 10
    
    # Load environment variables for health check
    if [ -f "$ENV_FILE" ]; then
        set -a
        source "$ENV_FILE"
        set +a
    fi
    
    # Check service health
    echo -e "\n${YELLOW}Checking service health...${NC}"
    sleep 5  # Give services a bit more time
    if curl -f http://localhost:${BACKEND_PORT:-8500}/health &> /dev/null; then
        echo -e "${GREEN}✓ Backend is healthy${NC}"
    else
        echo -e "${YELLOW}⚠ Backend is still starting up. Check logs with: docker-compose -f docker/docker-compose.prod.yml logs backend${NC}"
    fi
}

# Run main function
main

