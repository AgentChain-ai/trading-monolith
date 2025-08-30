#!/bin/bash
# AgentChain.Trade - Development Deployment Script

set -e

echo "🤖 AgentChain.Trade - Starting Development Environment"
echo "======================================================="

# Check if .env exists
if [ ! -f .env ]; then
    echo "⚠️  .env file not found. Copying from .env.example..."
    cp .env.example .env
    echo "📝 Please edit .env with your configuration before running again."
    exit 1
fi

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo "❌ Docker is not running. Please start Docker and try again."
    exit 1
fi

# Create data directory
echo "📁 Creating data directory..."
mkdir -p ./data

# Build and start services
echo "🔨 Building and starting services..."
docker-compose down --remove-orphans
docker-compose build --no-cache
docker-compose up -d

# Wait for services to be healthy
echo "⏳ Waiting for services to be healthy..."
sleep 10

# Check service health
echo "🔍 Checking service health..."
services=("backend" "frontend" "microservice" "redis")
for service in "${services[@]}"; do
    if docker-compose ps $service | grep -q "healthy\|Up"; then
        echo "✅ $service is running"
    else
        echo "❌ $service failed to start"
        docker-compose logs $service
    fi
done

echo ""
echo "🚀 AgentChain.Trade Development Environment Started!"
echo "======================================================="
echo "📊 Frontend:     http://localhost:3000"
echo "🔧 Backend API:  http://localhost:8000"
echo "⚡ Microservice: http://localhost:3002"
echo "📈 Prometheus:   http://localhost:9090"
echo "📊 Grafana:      http://localhost:3001 (admin/admin)"
echo ""
echo "📝 View logs:    docker-compose logs -f [service-name]"
echo "🛑 Stop all:     docker-compose down"
echo ""
