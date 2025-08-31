from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging
import os
from datetime import datetime
from dotenv import load_dotenv

from .database import engine
from .models import Base
from .database import seed_default_tokens, seed_managed_wallets
from .services.mcp_client import MCPClient
from .services.feature_extractor import FeatureExtractor
from .services.ml_engine import MLEngine
from .services.thesis_composer import ThesisComposer
from .services.gecko_client import GeckoTerminalClient
from .services.scheduler_service import start_trading_scheduler, stop_trading_scheduler
from .api.routes import router
from .utils.monitoring import setup_monitoring, metrics_collector, performance_monitor

# Load environment variables from .env file
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s:%(lineno)d %(message)s"
)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting NTM Trading Signal Engine...")
    
    # Create database tables
    Base.metadata.create_all(bind=engine)
    
    # Seed default tokens
    seed_default_tokens()
    
    # Initialize managed wallets (optional - fails gracefully if microservice unavailable)
    try:
        seed_managed_wallets()
    except Exception as e:
        logger.warning(f"Could not initialize managed wallets: {e}")
        logger.info("Managed wallets can be initialized later via /api/v1/deposit/initialize")
    
    # Initialize services
    app.state.mcp_client = MCPClient()
    app.state.feature_extractor = FeatureExtractor()
    app.state.ml_engine = MLEngine()
    app.state.thesis_composer = ThesisComposer()
    app.state.gecko_client = GeckoTerminalClient()
    
    # Start automated trading scheduler
    import asyncio
    logger.info("Starting automated trading scheduler...")
    try:
        # Start scheduler as background task
        asyncio.create_task(start_trading_scheduler())
        logger.info("Automated trading scheduler started successfully")
    except Exception as e:
        logger.warning(f"Failed to start trading scheduler: {e}")
        logger.info("Trading scheduler can be started manually via /api/v1/scheduler/start")
    
    logger.info("NTM Engine initialized successfully")
    yield
    
    # Shutdown
    logger.info("Shutting down NTM Engine...")
    try:
        await stop_trading_scheduler()
        logger.info("Trading scheduler stopped")
    except Exception as e:
        logger.warning(f"Error stopping trading scheduler: {e}")

app = FastAPI(
    title="Narrative→Thesis Model (NTM) Trading Engine",
    description="AI-powered trading signal engine that transforms market narratives into actionable trading theses",
    version="1.0.0",
    lifespan=lifespan
)

# Setup monitoring middleware
app = setup_monitoring(app)

# Configure CORS with environment variable support
allowed_origins = [
    "http://localhost:3000", 
    "http://localhost:5173",  # React dev servers
    "https://agentchain.trade",  # Production frontend
    "https://www.agentchain.trade",  # Production frontend with www
    "https://app.agentchain.trade",  # Alternative subdomain
]

# Add custom origins from environment variable
custom_origins = os.getenv('CORS_ORIGINS', '').split(',')
for origin in custom_origins:
    if origin.strip():
        allowed_origins.append(origin.strip())

logger.info(f"CORS allowed origins: {allowed_origins}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(router, prefix="/api/v1")

@app.get("/")
async def root():
    return {
        "message": "Narrative→Thesis Model (NTM) Trading Engine",
        "version": "1.0.0",
        "status": "running",
        "timestamp": datetime.utcnow().isoformat()
    }

@app.get("/health")
async def health_check():
    from .utils.resilience import health_checker
    
    # Check external services
    services = {
        "database": "connected",
        "mcp_client": "ready" if await health_checker.check_http_service("mcp_server", "https://scraper.agentchain.trade//health", timeout=5) else "unhealthy",
        "ml_engine": "ready",
        "gecko_terminal": "ready" if await health_checker.check_http_service("gecko", "https://api.geckoterminal.com/api/v2/networks", timeout=5) else "unhealthy"
    }
    
    overall_health = all(status == "ready" or status == "connected" for status in services.values())
    
    return {
        "status": "healthy" if overall_health else "degraded",
        "timestamp": datetime.utcnow().isoformat(),
        "services": services,
        "stats": {
            "total_articles": 0,  # TODO: get from database
            "total_buckets": 0,   # TODO: get from database
            "total_labels": 0,    # TODO: get from database
        }
    }

@app.get("/metrics")
async def get_metrics():
    """Get application metrics summary"""
    return {
        "metrics": metrics_collector.get_metrics_summary(),
        "active_requests": performance_monitor.get_active_requests(),
        "timestamp": datetime.utcnow().isoformat()
    }

@app.get("/alerts")
async def get_alerts():
    """Get active alerts"""
    from .utils.monitoring import alert_manager
    return {
        "active_alerts": alert_manager.get_active_alerts(),
        "timestamp": datetime.utcnow().isoformat()
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)