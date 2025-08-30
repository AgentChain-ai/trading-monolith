from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import logging
from datetime import datetime, timedelta
from typing import Optional, List
from dotenv import load_dotenv

from .database import engine
from .models import Base
from .database import seed_default_tokens, seed_managed_wallets
from .services.mcp_client import MCPClient
from .services.feature_extractor import FeatureExtractor
from .services.ml_engine import MLEngine
from .services.thesis_composer import ThesisComposer
from .services.gecko_client import GeckoTerminalClient
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
    
    logger.info("NTM Engine initialized successfully")
    yield
    
    # Shutdown
    logger.info("Shutting down NTM Engine...")

app = FastAPI(
    title="Narrative→Thesis Model (NTM) Trading Engine",
    description="AI-powered trading signal engine that transforms market narratives into actionable trading theses",
    version="1.0.0",
    lifespan=lifespan
)

# Setup monitoring middleware
app = setup_monitoring(app)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000", 
        "http://localhost:5173",  # React dev servers
        "https://agentchain.trade",  # Production frontend
        "https://www.agentchain.trade",  # Production frontend with www
        "https://app.agentchain.trade",  # Alternative subdomain
    ],
    allow_credentials=True,
    allow_methods=["*"],
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