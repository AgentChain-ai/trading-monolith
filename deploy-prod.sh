#!/bin/bash
# AgentChain.Trade - Production Deployment Script

set -e

echo "🤖 AgentChain.Trade - Production Deployment"
echo "============================================"

# Check if running as root
if [ "$EUID" -eq 0 ]; then
    echo "❌ Do not run this script as root for security reasons."
    exit 1
fi

# Check if .env exists
if [ ! -f .env ]; then
    echo "❌ .env file not found. Please create from .env.example and configure."
    exit 1
fi

# Validate required environment variables
required_vars=("GROQ_API_KEY" "AVALANCHE_RPC_URL" "FUJI_RPC_URL" "GRAFANA_ADMIN_PASSWORD")
for var in "${required_vars[@]}"; do
    if [ -z "${!var}" ]; then
        echo "❌ Required environment variable $var is not set."
        exit 1
    fi
done

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo "❌ Docker is not running. Please start Docker and try again."
    exit 1
fi

# Create necessary directories
echo "📁 Creating production directories..."
mkdir -p ./data ./logs
chmod 755 ./data ./logs

# Pull latest images
echo "📥 Pulling latest base images..."
docker compose -f docker-compose.prod.yml pull redis prometheus grafana

# Build production images
echo "🔨 Building production images..."
docker compose -f docker-compose.prod.yml build --no-cache

# Stop existing containers
echo "🛑 Stopping existing containers..."
docker compose -f docker-compose.prod.yml down --remove-orphans

# Start production services
echo "🚀 Starting production services..."
docker compose -f docker-compose.prod.yml up -d

# Wait for services
echo "⏳ Waiting for services to start..."
sleep 30

# Health check
echo "🔍 Performing health checks..."
services=("backend" "frontend" "microservice" "redis")
all_healthy=true

for service in "${services[@]}"; do
    if docker compose -f docker-compose.prod.yml ps $service | grep -q "healthy\|Up"; then
        echo "✅ $service is healthy"
    else
        echo "❌ $service is not healthy"
        all_healthy=false
    fi
done

if [ "$all_healthy" = true ]; then
    echo ""
    echo "🎉 Production Deployment Successful!"
    echo "===================================="
    echo "🌐 Application:  http://localhost"
    echo "📊 Monitoring:   http://localhost:9090 (Prometheus)"
    echo "📈 Dashboards:   http://localhost:3001 (Grafana)"
    echo ""
    echo "📝 Monitor logs: docker compose -f docker-compose.prod.yml logs -f"
    echo "🔄 Update:       ./deploy-prod.sh"
    echo "🛑 Stop:         docker compose -f docker-compose.prod.yml down"
else
    echo ""
    echo "❌ Deployment failed. Check service logs:"
    echo "docker compose -f docker-compose.prod.yml logs"
    exit 1
fi
