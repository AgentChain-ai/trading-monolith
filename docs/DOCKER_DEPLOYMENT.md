# 🐳 AgentChain.Trade - Docker Deployment Guide

This guide covers containerized deployment of the complete AgentChain.Trade platform using Docker and Docker Compose.

## 📋 Prerequisites

- **Docker Engine** 20.10+
- **Docker Compose** 2.0+
- **4GB+ RAM** available for containers
- **10GB+ Disk Space** for images and data

## 🏗️ Container Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Docker Network                           │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │
│  │   Frontend  │  │   Backend   │  │ Microservice│         │
│  │   (Nginx)   │  │  (FastAPI)  │  │    (Bun)    │         │
│  │   Port 80   │  │  Port 8000  │  │  Port 3002  │         │
│  └─────────────┘  └─────────────┘  └─────────────┘         │
│         │                 │                 │              │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │
│  │    Redis    │  │ Prometheus  │  │   Grafana   │         │
│  │  Port 6379  │  │  Port 9090  │  │  Port 3001  │         │
│  └─────────────┘  └─────────────┘  └─────────────┘         │
└─────────────────────────────────────────────────────────────┘
```

## 🚀 Quick Start

### 1. Environment Setup

```bash
# Clone repository
git clone <repository-url>
cd trading-monolith

# Copy environment template
cp .env.example .env

# Edit configuration
nano .env
```

### 2. Development Deployment

```bash
# Start development environment
./deploy-dev.sh

# Or manually:
docker compose up -d
```

### 3. Production Deployment

```bash
# Start production environment
./deploy-prod.sh

# Or manually:
docker compose -f docker-compose.prod.yml up -d
```

## 📊 Service Endpoints

| Service | Development | Production | Description |
|---------|------------|------------|-------------|
| **Frontend** | http://localhost:3000 | http://localhost | React UI with Material-UI |
| **Backend API** | https://api.agentchain.trade | http://localhost/api | FastAPI with AI engine |
| **Microservice** | http://localhost:3002 | http://localhost/microservice | Gasless transactions |
| **Prometheus** | http://localhost:9090 | http://localhost:9090 | Metrics collection |
| **Grafana** | http://localhost:3001 | http://localhost:3001 | Monitoring dashboards |

## 🔧 Container Configuration

### Backend (FastAPI)

```dockerfile
# Multi-stage build for optimization
FROM python:3.11-slim as builder
# Install dependencies in virtual environment
FROM python:3.11-slim as production
# Copy venv and run as non-root user
```

**Features:**
- Multi-stage build for smaller image size
- Non-root user for security
- Health checks and auto-restart
- Volume mounts for data persistence

### Frontend (React + Nginx)

```dockerfile
# Build stage with Node.js
FROM node:18-alpine as builder
# Production stage with Nginx
FROM nginx:alpine as production
```

**Features:**
- Optimized production build
- Nginx with security headers
- API proxy configuration
- Static asset caching

### Microservice (Bun)

```dockerfile
# Single-stage Bun runtime
FROM oven/bun:1 as base
# Non-root user and health checks
```

**Features:**
- Fast Bun runtime
- TypeScript compilation
- Built-in health monitoring
- Structured logging

## 🔐 Security Features

### Container Security

- **Non-root users** in all containers
- **Resource limits** to prevent DoS
- **Health checks** for reliability
- **Network isolation** between services

### Data Security

- **Environment variables** for secrets
- **Volume mounts** for persistent data
- **No sensitive data** in images
- **.dockerignore** for build security

## 📈 Monitoring & Observability

### Health Checks

All services include health check endpoints:

```bash
# Check service health
docker compose ps
docker compose logs [service-name]
```

### Metrics Collection

- **Prometheus** scrapes metrics from all services
- **Grafana** provides visualization dashboards
- **Custom metrics** for business logic

### Log Management

```bash
# View logs
docker compose logs -f backend
docker compose logs -f frontend
docker compose logs -f microservice

# Log rotation configured for production
```

## 🔄 Operations

### Starting Services

```bash
# Development
docker compose up -d

# Production
docker compose -f docker-compose.prod.yml up -d

# Specific service
docker compose up -d backend
```

### Stopping Services

```bash
# Stop all
docker compose down

# Stop and remove volumes
docker compose down -v

# Stop specific service
docker compose stop backend
```

### Updating Services

```bash
# Rebuild and restart
docker compose build --no-cache
docker compose up -d

# Rolling update
docker compose up -d --no-deps backend
```

### Scaling Services

```bash
# Scale horizontally
docker compose up -d --scale backend=3

# Production scaling with load balancer
docker compose -f docker-compose.prod.yml up -d --scale backend=2
```

## 🛠️ Troubleshooting

### Common Issues

**Service won't start:**
```bash
# Check logs
docker compose logs service-name

# Check health
docker compose ps

# Restart service
docker compose restart service-name
```

**Out of memory:**
```bash
# Check resource usage
docker stats

# Adjust limits in docker-compose.yml
deploy:
  resources:
    limits:
      memory: 1G
```

**Network issues:**
```bash
# Check network
docker network ls

# Recreate network
docker compose down
docker compose up -d
```

### Performance Tuning

**Resource Allocation:**
```yaml
deploy:
  resources:
    limits:
      cpus: '1.0'
      memory: 1G
    reservations:
      cpus: '0.5'
      memory: 512M
```

**Database Optimization:**
```bash
# SQLite optimizations applied in backend
# Redis memory limits configured
# Log rotation for disk space management
```

## 🔒 Security Hardening

### Production Checklist

- [ ] Change default passwords
- [ ] Enable SSL/TLS certificates
- [ ] Configure firewall rules
- [ ] Set up log monitoring
- [ ] Enable backup strategies
- [ ] Update base images regularly

### Security Scanning

```bash
# Scan images for vulnerabilities
docker scout cves

# Check for security issues
docker scout recommendations
```

## 📚 Additional Resources

- [Docker Compose Reference](https://docs.docker.com/compose/)
- [Production Deployment Guide](./PRODUCTION_DEPLOYMENT.md)
- [Monitoring Setup](../monitoring/README.md)
- [Security Best Practices](./SECURITY.md)

---

**Built for production deployment with enterprise-grade Docker practices** 🐳
