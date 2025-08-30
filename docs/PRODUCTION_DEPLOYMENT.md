# Production Deployment Guide
## NTM Trading Engine

This guide covers production deployment, monitoring, and operational best practices for the NTM Trading Engine.

---

## Table of Contents

1. [Pre-Deployment Checklist](#pre-deployment-checklist)
2. [Infrastructure Requirements](#infrastructure-requirements)
3. [Docker Production Setup](#docker-production-setup)
4. [Environment Configuration](#environment-configuration)
5. [Database Setup](#database-setup)
6. [Security Configuration](#security-configuration)
7. [Monitoring & Observability](#monitoring--observability)
8. [Load Balancing & Scaling](#load-balancing--scaling)
9. [Backup & Recovery](#backup--recovery)
10. [Troubleshooting](#troubleshooting)

---

## Pre-Deployment Checklist

### ✅ External Dependencies
- [ ] **Groq API**: Valid API key with sufficient credits
- [ ] **MCP Server**: Search-Scrape MCP Server accessible at `https://scraper.agentchain.trade/`
- [ ] **GeckoTerminal API**: Public API access confirmed
- [ ] **Network Access**: Outbound HTTPS access for API calls

### ✅ System Requirements
- [ ] **CPU**: Minimum 4 cores (8 recommended)
- [ ] **RAM**: Minimum 8GB (16GB recommended)
- [ ] **Storage**: Minimum 50GB SSD
- [ ] **OS**: Ubuntu 20.04+ or CentOS 8+

### ✅ Software Dependencies
- [ ] **Docker**: Version 20.10+
- [ ] **Docker Compose**: Version 2.0+
- [ ] **Python**: 3.9+ (if running without Docker)
- [ ] **Node.js**: 18+ (for frontend)

---

## Infrastructure Requirements

### Minimum Production Setup
```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Load Balancer │    │   Application   │    │    Database     │
│    (nginx)      │───▶│     Server      │───▶│   (SQLite)      │
│                 │    │   (FastAPI)     │    │                 │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

### Recommended Production Setup
```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Load Balancer │    │  App Server 1   │    │   Primary DB    │
│   (nginx/ALB)   │───▶│   (FastAPI)     │───▶│  (PostgreSQL)   │
│                 │    └─────────────────┘    │                 │
│                 │    ┌─────────────────┐    └─────────────────┘
│                 │───▶│  App Server 2   │             │
└─────────────────┘    │   (FastAPI)     │             │
                       └─────────────────┘             │
                       ┌─────────────────┐             │
                       │     Redis       │◀────────────┘
                       │    (Cache)      │
                       └─────────────────┘
```

---

## Docker Production Setup

### 1. Create Production Docker Compose

```yaml
# docker-compose.prod.yml
version: '3.8'

services:
  backend:
    build:
      context: ./backend
      dockerfile: Dockerfile.prod
    environment:
      - ENVIRONMENT=production
      - DATABASE_URL=postgresql://user:pass@db:5432/ntm_trading
      - REDIS_URL=redis://redis:6379
      - GROQ_API_KEY=${GROQ_API_KEY}
    depends_on:
      - db
      - redis
    volumes:
      - ./data:/app/data
      - ./logs:/app/logs
    networks:
      - ntm-network
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "https://api.agentchain.trade/health"]
      interval: 30s
      timeout: 10s
      retries: 3

  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile.prod
    depends_on:
      - backend
    networks:
      - ntm-network
    restart: unless-stopped

  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf
      - ./ssl:/etc/ssl/certs
    depends_on:
      - backend
      - frontend
    networks:
      - ntm-network
    restart: unless-stopped

  db:
    image: postgres:15-alpine
    environment:
      POSTGRES_DB: ntm_trading
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./backups:/backups
    networks:
      - ntm-network
    restart: unless-stopped
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER}"]
      interval: 10s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    command: redis-server --appendonly yes --requirepass ${REDIS_PASSWORD}
    volumes:
      - redis_data:/data
    networks:
      - ntm-network
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 3s
      retries: 3

  prometheus:
    image: prom/prometheus:latest
    ports:
      - "9090:9090"
    volumes:
      - ./monitoring/prometheus.yml:/etc/prometheus/prometheus.yml
      - prometheus_data:/prometheus
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
      - '--storage.tsdb.path=/prometheus'
      - '--web.console.libraries=/etc/prometheus/console_libraries'
      - '--web.console.templates=/etc/prometheus/consoles'
    networks:
      - ntm-network
    restart: unless-stopped

  grafana:
    image: grafana/grafana:latest
    ports:
      - "3000:3000"
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=${GRAFANA_PASSWORD}
    volumes:
      - grafana_data:/var/lib/grafana
      - ./monitoring/grafana/dashboards:/var/lib/grafana/dashboards
    networks:
      - ntm-network
    restart: unless-stopped

volumes:
  postgres_data:
  redis_data:
  prometheus_data:
  grafana_data:

networks:
  ntm-network:
    driver: bridge
```

### 2. Create Production Dockerfile

```dockerfile
# backend/Dockerfile.prod
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV ENVIRONMENT=production

# Create app directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create non-root user
RUN adduser --disabled-password --gecos '' appuser && chown -R appuser:appuser /app
USER appuser

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
  CMD curl -f https://api.agentchain.trade/health || exit 1

# Run application
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "4", "--worker-class", "uvicorn.workers.UvicornWorker", "--timeout", "120", "--keep-alive", "2", "--max-requests", "1000", "--max-requests-jitter", "50", "app.main:app"]
```

---

## Environment Configuration

### 1. Production Environment Variables

```bash
# .env.prod
# Application
ENVIRONMENT=production
DEBUG=false
LOG_LEVEL=INFO

# Database
DATABASE_URL=postgresql://ntm_user:secure_password@localhost:5432/ntm_trading_prod
REDIS_URL=redis://:redis_password@localhost:6379/0

# External APIs
GROQ_API_KEY=your_groq_api_key_here
MCP_SERVER_URL=https://scraper.agentchain.trade/
GECKO_TERMINAL_URL=https://api.geckoterminal.com/api/v2

# Security
SECRET_KEY=your_very_secure_secret_key_here
JWT_SECRET_KEY=your_jwt_secret_key_here
API_KEY_SALT=your_api_key_salt_here

# Rate Limiting
GROQ_RATE_LIMIT=2.0
GECKO_RATE_LIMIT=10.0
MCP_RATE_LIMIT=5.0

# Circuit Breaker
GROQ_FAILURE_THRESHOLD=3
GECKO_FAILURE_THRESHOLD=5
MCP_FAILURE_THRESHOLD=3

# Cache
CACHE_TTL_PRICE_DATA=300
CACHE_TTL_EVENT_CLASSIFICATION=3600
CACHE_TTL_SEARCH_RESULTS=1800

# Monitoring
ENABLE_METRICS=true
METRICS_PORT=9000
SENTRY_DSN=your_sentry_dsn_here
```

### 2. Nginx Configuration

```nginx
# nginx.conf
events {
    worker_connections 1024;
}

http {
    upstream backend {
        server backend:8000;
        keepalive 32;
    }

    upstream frontend {
        server frontend:3000;
        keepalive 32;
    }

    server {
        listen 80;
        server_name your-domain.com;

        # Security headers
        add_header X-Frame-Options DENY;
        add_header X-Content-Type-Options nosniff;
        add_header X-XSS-Protection "1; mode=block";
        add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;

        # API routes
        location /api/ {
            proxy_pass http://backend;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            proxy_connect_timeout 60s;
            proxy_send_timeout 60s;
            proxy_read_timeout 60s;
        }

        # Health check
        location /health {
            proxy_pass http://backend/health;
            access_log off;
        }

        # Frontend routes
        location / {
            proxy_pass http://frontend;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }

        # Static files
        location /static/ {
            alias /app/static/;
            expires 1y;
            add_header Cache-Control "public, immutable";
        }
    }

    # Rate limiting
    limit_req_zone $binary_remote_addr zone=api:10m rate=10r/s;
    limit_req_zone $binary_remote_addr zone=ingest:10m rate=1r/s;

    server {
        listen 80;
        
        location /api/v1/ingest {
            limit_req zone=ingest burst=5 nodelay;
            proxy_pass http://backend;
        }

        location /api/ {
            limit_req zone=api burst=20 nodelay;
            proxy_pass http://backend;
        }
    }
}
```

---

## Database Setup

### 1. Production Database Migration

```bash
# Run database migration
python scripts/migrate_database.py migrate

# Verify migration
python scripts/migrate_database.py history

# Create backup
python scripts/migrate_database.py backup
```

### 2. Database Backup Script

```bash
#!/bin/bash
# backup_db.sh

set -e

DB_NAME="ntm_trading"
BACKUP_DIR="/backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/ntm_trading_${TIMESTAMP}.sql"

# Create backup directory
mkdir -p $BACKUP_DIR

# Create database backup
pg_dump -h localhost -U $POSTGRES_USER -d $DB_NAME > $BACKUP_FILE

# Compress backup
gzip $BACKUP_FILE

# Keep only last 30 days of backups
find $BACKUP_DIR -name "*.sql.gz" -mtime +30 -delete

echo "Backup created: ${BACKUP_FILE}.gz"
```

### 3. Database Monitoring

```sql
-- Monitor database performance
SELECT 
    schemaname,
    tablename,
    n_tup_ins as inserts,
    n_tup_upd as updates,
    n_tup_del as deletes,
    n_live_tup as live_tuples,
    n_dead_tup as dead_tuples
FROM pg_stat_user_tables 
ORDER BY n_tup_ins + n_tup_upd + n_tup_del DESC;

-- Monitor query performance  
SELECT 
    query,
    calls,
    total_time,
    mean_time,
    rows
FROM pg_stat_statements 
ORDER BY total_time DESC 
LIMIT 10;
```

---

## Security Configuration

### 1. API Key Management

```python
# Generate secure API keys
import secrets
import hashlib

def generate_api_key():
    return secrets.token_urlsafe(32)

def hash_api_key(api_key, salt):
    return hashlib.pbkdf2_hmac('sha256', api_key.encode(), salt.encode(), 100000)
```

### 2. SSL/TLS Setup

```bash
# Generate SSL certificate (Let's Encrypt)
sudo certbot --nginx -d your-domain.com

# Or use self-signed for development
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout ssl/private.key -out ssl/certificate.crt
```

### 3. Security Middleware

```python
# backend/app/middleware/security.py
from fastapi import Request
from fastapi.middleware.base import BaseHTTPMiddleware
import time
import logging

class SecurityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start_time = time.time()
        
        # Add security headers
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        
        # Log request
        process_time = time.time() - start_time
        logging.info(f"{request.method} {request.url.path} - {response.status_code} - {process_time:.2f}s")
        
        return response
```

---

## Monitoring & Observability

### 1. Application Metrics

```python
# backend/app/utils/metrics.py
from prometheus_client import Counter, Histogram, Gauge
import time

# Request metrics
REQUEST_COUNT = Counter('requests_total', 'Total requests', ['method', 'endpoint', 'status'])
REQUEST_DURATION = Histogram('request_duration_seconds', 'Request duration')
ACTIVE_CONNECTIONS = Gauge('active_connections', 'Active connections')

# Business metrics
ARTICLES_PROCESSED = Counter('articles_processed_total', 'Total articles processed')
PREDICTIONS_MADE = Counter('predictions_made_total', 'Total predictions made')
API_CALLS = Counter('external_api_calls_total', 'External API calls', ['service', 'status'])

# Circuit breaker metrics
CIRCUIT_BREAKER_STATE = Gauge('circuit_breaker_state', 'Circuit breaker state', ['service'])
```

### 2. Health Check Endpoint

```python
# backend/app/api/health.py
from fastapi import APIRouter
from ..utils.resilience import health_checker

router = APIRouter()

@router.get("/health")
async def health_check():
    # Check all external services
    services = {
        "mcp_server": await health_checker.check_http_service("mcp_server", "https://scraper.agentchain.trade//health"),
        "groq_api": True,  # Assume healthy if no recent failures
        "gecko_terminal": await health_checker.check_http_service("gecko", "https://api.geckoterminal.com/api/v2/networks")
    }
    
    overall_health = all(services.values())
    
    return {
        "status": "healthy" if overall_health else "degraded",
        "services": services,
        "timestamp": datetime.utcnow().isoformat()
    }
```

### 3. Grafana Dashboard Configuration

```json
{
  "dashboard": {
    "title": "NTM Trading Engine",
    "panels": [
      {
        "title": "Request Rate",
        "type": "graph",
        "targets": [
          {
            "expr": "rate(requests_total[5m])",
            "legendFormat": "{{method}} {{endpoint}}"
          }
        ]
      },
      {
        "title": "Response Time",
        "type": "graph", 
        "targets": [
          {
            "expr": "histogram_quantile(0.95, rate(request_duration_seconds_bucket[5m]))",
            "legendFormat": "95th percentile"
          }
        ]
      },
      {
        "title": "Circuit Breaker Status",
        "type": "stat",
        "targets": [
          {
            "expr": "circuit_breaker_state",
            "legendFormat": "{{service}}"
          }
        ]
      }
    ]
  }
}
```

---

## Load Balancing & Scaling

### 1. Horizontal Scaling

```bash
# Scale backend services
docker-compose -f docker-compose.prod.yml up -d --scale backend=3

# Add load balancer configuration
# Update nginx upstream block with multiple backends
```

### 2. Auto-scaling Configuration

```yaml
# kubernetes/deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ntm-backend
spec:
  replicas: 2
  selector:
    matchLabels:
      app: ntm-backend
  template:
    metadata:
      labels:
        app: ntm-backend
    spec:
      containers:
      - name: backend
        image: ntm-backend:latest
        resources:
          requests:
            memory: "512Mi"
            cpu: "500m"
          limits:
            memory: "1Gi"
            cpu: "1000m"
---
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: ntm-backend-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: ntm-backend
  minReplicas: 2
  maxReplicas: 10
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
```

---

## Backup & Recovery

### 1. Automated Backup Script

```bash
#!/bin/bash
# automated_backup.sh

BACKUP_DIR="/backups"
DB_NAME="ntm_trading"
RETENTION_DAYS=30

# Create daily backup
pg_dump -h $DB_HOST -U $DB_USER $DB_NAME | gzip > "$BACKUP_DIR/daily_$(date +%Y%m%d).sql.gz"

# Create weekly backup (every Sunday)
if [ $(date +%w) -eq 0 ]; then
    pg_dump -h $DB_HOST -U $DB_USER $DB_NAME | gzip > "$BACKUP_DIR/weekly_$(date +%Y%m%d).sql.gz"
fi

# Create monthly backup (1st of month)
if [ $(date +%d) -eq 01 ]; then
    pg_dump -h $DB_HOST -U $DB_USER $DB_NAME | gzip > "$BACKUP_DIR/monthly_$(date +%Y%m%d).sql.gz"
fi

# Clean up old backups
find $BACKUP_DIR -name "daily_*.sql.gz" -mtime +$RETENTION_DAYS -delete
find $BACKUP_DIR -name "weekly_*.sql.gz" -mtime +90 -delete  # Keep 3 months
find $BACKUP_DIR -name "monthly_*.sql.gz" -mtime +365 -delete  # Keep 1 year
```

### 2. Disaster Recovery Plan

```bash
# Recovery procedure
# 1. Stop the application
docker-compose -f docker-compose.prod.yml down

# 2. Restore database from backup
gunzip -c /backups/backup_file.sql.gz | psql -h $DB_HOST -U $DB_USER $DB_NAME

# 3. Verify data integrity
python scripts/migrate_database.py test

# 4. Restart services
docker-compose -f docker-compose.prod.yml up -d

# 5. Verify system health
curl http://localhost/health
```

---

## Troubleshooting

### Common Issues & Solutions

#### 1. High Memory Usage
```bash
# Check memory usage
docker stats

# Optimize Python memory usage
export PYTHONMALLOC=malloc
export MALLOC_MMAP_THRESHOLD_=131072
export MALLOC_TRIM_THRESHOLD_=131072
export MALLOC_MMAP_MAX_=65536
```

#### 2. Circuit Breaker Trips
```bash
# Check circuit breaker status
curl https://api.agentchain.trade/api/v1/health

# Reset circuit breaker (manual intervention)
# Restart affected service or wait for timeout
```

#### 3. Database Performance Issues
```sql
-- Find slow queries
SELECT query, mean_time, calls 
FROM pg_stat_statements 
WHERE mean_time > 1000 
ORDER BY mean_time DESC;

-- Check for locks
SELECT * FROM pg_locks WHERE NOT granted;
```

#### 4. External API Failures
```bash
# Check API connectivity
curl -I https://scraper.agentchain.trade//health
curl -I https://api.geckoterminal.com/api/v2/networks

# Check rate limiting
tail -f logs/app.log | grep "rate limit"
```

### Log Analysis

```bash
# Application logs
docker-compose logs -f backend

# Database logs
docker-compose logs -f db

# Nginx logs
docker-compose logs -f nginx

# Filter for errors
docker-compose logs backend | grep ERROR

# Monitor real-time metrics
watch -n 5 'curl -s http://localhost:9090/api/v1/query?query=rate(requests_total[5m])'
```

---

## Performance Optimization

### 1. Database Optimization

```sql
-- Add indexes for common queries
CREATE INDEX CONCURRENTLY idx_articles_token_created ON articles(token, created_at);
CREATE INDEX CONCURRENTLY idx_buckets_token_ts ON buckets(token, bucket_ts);
CREATE INDEX CONCURRENTLY idx_labels_binary_ts ON labels(label_binary, created_at);

-- Optimize queries
ANALYZE;
VACUUM ANALYZE;
```

### 2. Application Optimization

```python
# Connection pooling
from sqlalchemy.pool import QueuePool

engine = create_engine(
    DATABASE_URL,
    poolclass=QueuePool,
    pool_size=20,
    max_overflow=30,
    pool_pre_ping=True,
    pool_recycle=3600
)

# Async optimization
import asyncio
async def process_batch(articles):
    tasks = [process_article(article) for article in articles]
    return await asyncio.gather(*tasks, return_exceptions=True)
```

### 3. Caching Strategy

```python
# Multi-level caching
from cachetools import TTLCache
import redis

# L1: In-memory cache
l1_cache = TTLCache(maxsize=1000, ttl=300)

# L2: Redis cache  
redis_client = redis.Redis.from_url(REDIS_URL)

async def get_cached_data(key):
    # Check L1 cache first
    if key in l1_cache:
        return l1_cache[key]
    
    # Check L2 cache
    data = redis_client.get(key)
    if data:
        l1_cache[key] = data
        return data
    
    return None
```

---

This production deployment guide ensures your NTM Trading Engine runs reliably, securely, and efficiently in production environments.