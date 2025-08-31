from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
import logging
import psutil
import asyncio

from ..database import get_db, SessionLocal
from ..models import Article, Bucket, Label, TrackedToken, UserWallet, ManagedWallet, UserDeposit, UserBalance
from ..services.mcp_client import MCPClient
from ..services.feature_extractor import FeatureExtractor
from ..services.ml_engine import MLEngine
from ..services.thesis_composer import ThesisComposer
from ..services.aggregator import NarrativeAggregator
from ..services.gecko_client import GeckoTerminalClient
from ..services.deposit_service import DepositService
from ..services.portfolio_service import PortfolioService
from ..services.scheduler_service import get_trading_scheduler
from pydantic import BaseModel
from ..utils.resilience import _circuit_breakers, health_checker, fallback_cache

logger = logging.getLogger(__name__)

# In-memory status tracking for ingestion progress
ingestion_status: Dict[str, Dict[str, Any]] = {}

router = APIRouter()

# Pydantic models for request/response
class IngestRequest(BaseModel):
    token: str
    hours_back: int = 24
    max_articles: int = 20

class FeedbackRequest(BaseModel):
    token: str
    bucket_ts: str
    actual_return: float

class PortfolioRequest(BaseModel):
    user_address: str
    
class RebalanceRequest(BaseModel):
    user_address: str
    force: bool = False

# Initialize services
portfolio_service = PortfolioService()

class PredictResponse(BaseModel):
    token: str
    probability_up: float
    confidence: str
    timestamp: str
    window_minutes: int
    feature_importance: dict
    features_used: dict

# Admin Token Management Models
class TrackedTokenCreate(BaseModel):
    symbol: str
    name: Optional[str] = None
    chain_id: Optional[int] = None
    contract_address: Optional[str] = None
    gecko_id: Optional[str] = None
    auto_analysis: bool = False
    analysis_interval_hours: int = 6
    added_by: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

class TrackedTokenUpdate(BaseModel):
    name: Optional[str] = None
    chain_id: Optional[int] = None
    contract_address: Optional[str] = None
    gecko_id: Optional[str] = None
    is_active: Optional[bool] = None
    auto_analysis: Optional[bool] = None
    analysis_interval_hours: Optional[int] = None
    metadata: Optional[Dict[str, Any]] = None

class TrackedTokenResponse(BaseModel):
    id: int
    symbol: str
    name: Optional[str]
    chain_id: Optional[int]
    contract_address: Optional[str]
    gecko_id: Optional[str]
    is_active: bool
    auto_analysis: bool
    analysis_interval_hours: int
    last_analysis_at: Optional[str]
    added_by: Optional[str]
    metadata: Optional[Dict[str, Any]]
    created_at: str
    updated_at: str

class ThesisResponse(BaseModel):
    token: str
    timestamp: str
    window_minutes: int
    narrative_heat: float
    consensus: float
    top_event: str
    p_up_60m: float
    confidence: str
    hype_velocity: float
    risk_polarity: float
    reasoning: List[str]
    guardrails: List[str]
    evidence: List[dict]

# Deposit System Models
class DepositAddressRequest(BaseModel):
    user_wallet_address: str
    chain_id: int

class DepositAddressResponse(BaseModel):
    user_wallet_address: str
    chain_id: int
    chain_name: str
    deposit_address: str
    smart_account: str
    eoa_address: str

class RecordDepositRequest(BaseModel):
    user_wallet_address: str
    chain_id: int
    token_symbol: str
    amount: str
    tx_hash: str

class DepositStatusUpdate(BaseModel):
    tx_hash: str
    status: str  # "pending", "confirmed", "failed"

class UserBalanceResponse(BaseModel):
    chain_id: int
    chain_name: str
    token_symbol: str
    balance: str
    updated_at: str

class SupportedChainResponse(BaseModel):
    chain_id: int
    name: str
    native_currency: str

class ManagedWalletResponse(BaseModel):
    chain_id: int
    chain_name: str
    smart_account: Optional[str] = None
    eoa_address: Optional[str] = None

# Initialize services (these will be injected by FastAPI lifespan)
async def get_mcp_client():
    return MCPClient()

async def get_feature_extractor():
    return FeatureExtractor()

async def get_ml_engine():
    return MLEngine()

async def get_thesis_composer():
    return ThesisComposer()

async def get_aggregator():
    return NarrativeAggregator()

async def get_gecko_client():
    return GeckoTerminalClient()

@router.get("/ingestion-status/{token}")
async def get_ingestion_status(token: str):
    """Get the current ingestion status for a token"""
    status = ingestion_status.get(token.upper(), {
        "status": "idle",
        "message": "No ingestion in progress",
        "progress": 0,
        "started_at": None,
        "articles_processed": 0,
        "articles_total": 0
    })
    return status

def update_ingestion_status(token: str, status: str, message: str, progress: int = 0, **kwargs):
    """Update ingestion status for a token"""
    if token.upper() not in ingestion_status:
        ingestion_status[token.upper()] = {}
    
    ingestion_status[token.upper()].update({
        "status": status,
        "message": message,
        "progress": progress,
        "updated_at": datetime.utcnow().isoformat(),
        **kwargs
    })

@router.post("/ingest")
async def ingest_token_data(
    request: IngestRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Ingest and process articles for a token
    
    This endpoint:
    1. Searches for token-related articles
    2. Scrapes article content
    3. Extracts features from each article
    4. Stores articles in database
    5. Aggregates articles into buckets
    """
    try:
        logger.info(f"Starting ingestion for token: {request.token}")
        
        # Initialize status tracking
        update_ingestion_status(
            request.token, 
            "starting", 
            "Initializing ingestion process...", 
            progress=5,
            started_at=datetime.utcnow().isoformat(),
            articles_processed=0,
            articles_total=request.max_articles
        )
        
        # Add the actual ingestion work to background tasks
        background_tasks.add_task(
            process_token_ingestion,
            request.token,
            request.hours_back,
            request.max_articles
        )
        
        return {
            "message": f"Ingestion started for {request.token}",
            "token": request.token,
            "hours_back": request.hours_back,
            "max_articles": request.max_articles,
            "status": "processing"
        }
        
    except Exception as e:
        logger.error(f"Error starting ingestion for {request.token}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

async def process_token_ingestion(token: str, hours_back: int, max_articles: int):
    """Background task for processing token ingestion"""
    db = None
    try:
        logger.info(f"Starting background ingestion for {token} (hours_back={hours_back}, max_articles={max_articles})")
        
        # Update status: Starting search
        update_ingestion_status(token, "searching", "Searching for articles...", progress=10)
        
        # Initialize services
        mcp_client = MCPClient()
        feature_extractor = FeatureExtractor()
        aggregator = NarrativeAggregator()
        
        # 1. Get articles from MCP server
        logger.info(f"Fetching articles for {token}")
        scraped_articles = await mcp_client.get_token_articles(token, hours_back, max_articles)
        
        if not scraped_articles:
            logger.warning(f"No articles found for {token}")
            update_ingestion_status(token, "completed", "No articles found", progress=100)
            return
        
        logger.info(f"Fetched {len(scraped_articles)} articles for {token}")
        update_ingestion_status(
            token, 
            "processing", 
            f"Processing {len(scraped_articles)} articles...", 
            progress=25,
            articles_total=len(scraped_articles)
        )
        
        # 2. Process each article
        processed_count = 0
        failed_count = 0
        
        # Use SessionLocal for background tasks
        db = SessionLocal()
        
        try:
            for i, scraped_article in enumerate(scraped_articles, 1):
                try:
                    logger.debug(f"Processing article {i}/{len(scraped_articles)}: {scraped_article.url}")
                    
                    # Check if article already exists
                    existing_article = db.query(Article).filter(
                        Article.url == scraped_article.url
                    ).first()
                    
                    if existing_article:
                        logger.debug(f"Article already exists: {scraped_article.url}")
                        continue
                    
                    # Extract features
                    logger.debug(f"Extracting features for article: {scraped_article.title[:50]}...")
                    features = await feature_extractor.extract_features(
                        scraped_article.__dict__, token
                    )
                    logger.debug(f"Features extracted: sentiment={features.sentiment_score:.3f}, final_weight={features.final_weight:.3f}")
                    
                    # Parse published date
                    published_at = None
                    if scraped_article.published_at:
                        try:
                            published_at = datetime.fromisoformat(
                                scraped_article.published_at.replace('Z', '+00:00')
                            )
                        except Exception as date_error:
                            logger.warning(f"Failed to parse date '{scraped_article.published_at}': {date_error}")
                    
                    # Create article record
                    article = Article(
                        token=token,
                        url=scraped_article.url,
                        site_name=scraped_article.site_name,
                        title=scraped_article.title,
                        published_at=published_at,
                        clean_content=scraped_article.clean_content,
                        word_count=scraped_article.word_count,
                        event_probs=features.event_probs,
                        sentiment_score=features.sentiment_score,
                        source_trust=features.source_trust,
                        recency_decay=features.recency_decay,
                        novelty_score=features.novelty_score,
                        proof_bonus=features.proof_bonus,
                        final_weight=features.final_weight
                    )
                    
                    db.add(article)
                    processed_count += 1
                    logger.debug(f"Article added to database: {article.title[:50]}...")
                    
                    # Update progress
                    progress = 25 + (processed_count / len(scraped_articles)) * 50  # 25-75% for processing
                    update_ingestion_status(
                        token, 
                        "processing", 
                        f"Processed {processed_count}/{len(scraped_articles)} articles", 
                        progress=int(progress),
                        articles_processed=processed_count
                    )
                    
                except Exception as e:
                    failed_count += 1
                    logger.error(f"Error processing article {scraped_article.url}: {type(e).__name__}: {e}", exc_info=True)
                    continue
            
            # Commit articles
            if processed_count > 0:
                logger.info(f"Committing {processed_count} articles to database for {token}")
                update_ingestion_status(token, "aggregating", "Creating analysis buckets...", progress=80)
                
                db.commit()
                logger.info(f"Successfully processed {processed_count} articles for {token} ({failed_count} failed)")
                
                # 3. Aggregate into buckets
                logger.info(f"Starting aggregation for {token}")
                try:
                    buckets = await aggregator.process_token_articles(token, hours_back)
                    logger.info(f"Created/updated {len(buckets)} buckets for {token}")
                    
                    # Update completion status
                    update_ingestion_status(
                        token, 
                        "completed", 
                        f"Analysis completed! {processed_count} articles processed, {len(buckets)} analysis buckets created", 
                        progress=100,
                        articles_processed=processed_count,
                        buckets_created=len(buckets)
                    )
                except Exception as agg_error:
                    logger.error(f"Error during aggregation for {token}: {type(agg_error).__name__}: {agg_error}", exc_info=True)
                    update_ingestion_status(token, "error", f"Error during aggregation: {str(agg_error)}", progress=90)
            else:
                logger.warning(f"No new articles processed for {token} - nothing to commit")
                update_ingestion_status(token, "completed", "No new articles found to process", progress=100)
            
        except Exception as db_error:
            logger.error(f"Database error during ingestion for {token}: {type(db_error).__name__}: {db_error}", exc_info=True)
            if db:
                db.rollback()
        finally:
            if db:
                db.close()
                logger.debug(f"Database session closed for {token}")
            
    except Exception as e:
        logger.error(f"Critical error in background ingestion for {token}: {type(e).__name__}: {e}", exc_info=True)
        update_ingestion_status(token, "error", f"Critical error: {str(e)}", progress=0)

@router.get("/features/{token}")
async def get_token_features(
    token: str,
    bucket_ts: Optional[str] = None,
    hours_back: int = 24,
    db: Session = Depends(get_db)
):
    """Get aggregated features for a token"""
    try:
        aggregator = NarrativeAggregator()
        
        if bucket_ts:
            # Get specific bucket
            target_time = datetime.fromisoformat(bucket_ts.replace('Z', '+00:00'))
            bucket = db.query(Bucket).filter(
                Bucket.token == token,
                Bucket.bucket_ts == target_time
            ).first()
            
            if not bucket:
                raise HTTPException(status_code=404, detail="Bucket not found")
                
            return bucket.to_dict()
        else:
            # Get recent buckets
            since = datetime.utcnow() - timedelta(hours=hours_back)
            buckets = db.query(Bucket).filter(
                Bucket.token == token,
                Bucket.bucket_ts >= since
            ).order_by(Bucket.bucket_ts.desc()).all()
            
            return {
                "token": token,
                "buckets": [bucket.to_dict() for bucket in buckets],
                "count": len(buckets)
            }
            
    except Exception as e:
        logger.error(f"Error getting features for {token}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/predict/{token}")
async def predict_token_movement(
    token: str,
    horizon_minutes: int = 60,
    db: Session = Depends(get_db)
):
    """Make trading prediction for a token"""
    try:
        # Get latest bucket
        latest_bucket = db.query(Bucket).filter(
            Bucket.token == token
        ).order_by(Bucket.bucket_ts.desc()).first()
        
        if not latest_bucket:
            raise HTTPException(status_code=404, detail="No data found for token")
        
        # Initialize ML engine and make prediction
        ml_engine = MLEngine()
        bucket_data = latest_bucket.to_dict()
        prediction = await ml_engine.predict(bucket_data)
        
        return PredictResponse(
            token=token,
            probability_up=prediction.probability_up,
            confidence=prediction.confidence,
            timestamp=datetime.utcnow().isoformat(),
            window_minutes=horizon_minutes,
            feature_importance=prediction.feature_importance,
            features_used=prediction.features_used
        )
        
    except Exception as e:
        logger.error(f"Error predicting for {token}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/thesis/{token}")
async def get_trading_thesis(
    token: str,
    window_minutes: int = 60,
    db: Session = Depends(get_db)
):
    """Get complete trading thesis for a token"""
    try:
        # Get latest bucket
        latest_bucket = db.query(Bucket).filter(
            Bucket.token == token
        ).order_by(Bucket.bucket_ts.desc()).first()
        
        if not latest_bucket:
            raise HTTPException(status_code=404, detail="No data found for token")
        
        # Get ML prediction
        ml_engine = MLEngine()
        bucket_data = latest_bucket.to_dict()
        prediction = await ml_engine.predict(bucket_data)
        
        # Compose thesis
        thesis_composer = ThesisComposer()
        thesis = await thesis_composer.compose_thesis(
            token, bucket_data, prediction, window_minutes
        )
        
        return thesis_composer.to_dict(thesis)
        
    except Exception as e:
        logger.error(f"Error generating thesis for {token}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/feedback")
async def submit_feedback(
    request: FeedbackRequest,
    db: Session = Depends(get_db)
):
    """Submit feedback for model learning"""
    try:
        # Parse timestamp
        bucket_ts = datetime.fromisoformat(request.bucket_ts.replace('Z', '+00:00'))
        
        # Check if label already exists
        existing_label = db.query(Label).filter(
            Label.token == request.token,
            Label.bucket_ts == bucket_ts
        ).first()
        
        # Determine binary label (1 if return > 0.5%, 0 otherwise)
        label_binary = 1 if request.actual_return > 0.005 else 0
        
        if existing_label:
            # Update existing label
            existing_label.forward_return_60m = request.actual_return
            existing_label.label_binary = label_binary
        else:
            # Create new label
            new_label = Label(
                token=request.token,
                bucket_ts=bucket_ts,
                forward_return_60m=request.actual_return,
                label_binary=label_binary
            )
            db.add(new_label)
        
        db.commit()
        
        logger.info(f"Feedback recorded for {request.token} at {request.bucket_ts}: "
                   f"{request.actual_return:.3f} -> label {label_binary}")
        
        return {
            "message": "Feedback recorded successfully",
            "token": request.token,
            "bucket_ts": request.bucket_ts,
            "actual_return": request.actual_return,
            "label_binary": label_binary
        }
        
    except Exception as e:
        logger.error(f"Error recording feedback: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/dashboard/{token}")
async def get_dashboard_data(
    token: str,
    hours_back: int = 48,
    db: Session = Depends(get_db)
):
    """Get comprehensive dashboard data for a token"""
    try:
        since = datetime.utcnow() - timedelta(hours=hours_back)
        
        # Get buckets
        buckets = db.query(Bucket).filter(
            Bucket.token == token,
            Bucket.bucket_ts >= since
        ).order_by(Bucket.bucket_ts).all()
        
        # If no buckets found, return empty state structure
        if not buckets:
            logger.info(f"No buckets found for {token}, returning empty state")
            
            # Create default empty thesis structure
            empty_thesis = {
                "token": token,
                "timestamp": datetime.utcnow().isoformat(),
                "window_minutes": 60,
                "narrative_heat": 0.0,
                "consensus": 0.0,
                "top_event": "unknown",
                "p_up_60m": 0.5,
                "confidence": "LOW",
                "hype_velocity": 0.0,
                "risk_polarity": 0.0,
                "reasoning": [f"No data available for {token} - please ingest data first"],
                "guardrails": ["Insufficient data for analysis - avoid trading"],
                "evidence": [],
                "features_snapshot": {}
            }
            
            return {
                "token": token,
                "current_thesis": empty_thesis,
                "buckets": [],
                "recent_articles": [],
                "summary": {
                    "total_buckets": 0,
                    "avg_narrative_heat": 0.0,
                    "latest_consensus": 0.0,
                    "latest_risk_polarity": 0.0
                }
            }
        
        # Get latest prediction and thesis
        latest_bucket = buckets[-1]
        ml_engine = MLEngine()
        bucket_data = latest_bucket.to_dict()
        prediction = await ml_engine.predict(bucket_data)
        
        thesis_composer = ThesisComposer()
        thesis = await thesis_composer.compose_thesis(
            token, bucket_data, prediction, 60
        )
        
        # Get recent articles for evidence
        recent_articles = db.query(Article).filter(
            Article.token == token,
            Article.created_at >= since - timedelta(hours=6)
        ).order_by(Article.final_weight.desc()).limit(10).all()
        
        return {
            "token": token,
            "current_thesis": thesis_composer.to_dict(thesis),
            "buckets": [bucket.to_dict() for bucket in buckets],
            "recent_articles": [
                {
                    "title": article.title,
                    "url": article.url,
                    "site_name": article.site_name,
                    "sentiment_score": article.sentiment_score,
                    "final_weight": article.final_weight,
                    "event_probs": article.event_probs,
                    "created_at": article.created_at.isoformat() if article.created_at else None
                }
                for article in recent_articles
            ],
            "summary": {
                "total_buckets": len(buckets),
                "avg_narrative_heat": sum(b.narrative_heat or 0 for b in buckets) / len(buckets),
                "latest_consensus": latest_bucket.consensus,
                "latest_risk_polarity": latest_bucket.risk_polarity
            }
        }
        
    except HTTPException:
        # Re-raise HTTP exceptions (like 404)
        raise
    except Exception as e:
        logger.error(f"Error getting dashboard data for {token}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/train")
async def train_model(
    model_type: str = "lightgbm",
    background_tasks: BackgroundTasks = None
):
    """Train a new ML model"""
    try:
        if background_tasks:
            background_tasks.add_task(train_model_background, model_type)
            return {
                "message": f"Model training started for {model_type}",
                "status": "processing"
            }
        else:
            # Train synchronously (for testing)
            ml_engine = MLEngine()
            model_version = await ml_engine.train_model(model_type)
            
            if model_version:
                return {
                    "message": "Model trained successfully",
                    "model_version": model_version,
                    "model_type": model_type
                }
            else:
                raise HTTPException(status_code=400, detail="Model training failed")
                
    except Exception as e:
        logger.error(f"Error training model: {e}")
        raise HTTPException(status_code=500, detail=str(e))

async def train_model_background(model_type: str):
    """Background task for model training"""
    try:
        ml_engine = MLEngine()
        model_version = await ml_engine.train_model(model_type)
        
        if model_version:
            logger.info(f"Model {model_version} trained successfully in background")
        else:
            logger.error("Model training failed in background task")
            
    except Exception as e:
        logger.error(f"Error in background model training: {e}")

@router.get("/model/status")
async def get_model_status():
    """Get comprehensive model status and training information"""
    try:
        ml_engine = MLEngine()
        status = await ml_engine.get_model_status()
        
        return {
            "status": "success",
            "model_info": status,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error getting model status: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/model/auto-train")
async def trigger_auto_training(
    background_tasks: BackgroundTasks = None
):
    """Trigger automatic model training (with synthetic data if needed)"""
    try:
        if background_tasks:
            background_tasks.add_task(auto_train_model_background)
            return {
                "message": "Automatic model training started",
                "status": "processing"
            }
        else:
            # Train synchronously (for testing)
            ml_engine = MLEngine()
            model_version = await ml_engine._auto_train_model()
            
            if model_version:
                return {
                    "message": "Model auto-trained successfully",
                    "model_version": model_version,
                    "status": "success"
                }
            else:
                return {
                    "message": "Auto-training failed - insufficient data",
                    "status": "failed",
                    "suggestion": "Try ingesting more token data or wait for more labeled samples"
                }
                
    except Exception as e:
        logger.error(f"Error in auto-training: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/model/retrain-check")
async def check_and_retrain():
    """Check if model needs retraining and retrain if necessary"""
    try:
        ml_engine = MLEngine()
        retrain_success = await ml_engine.check_and_retrain_model()
        
        return {
            "retrain_performed": retrain_success,
            "message": "Model retrained successfully" if retrain_success else "No retraining needed or failed",
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error checking/retraining model: {e}")
        raise HTTPException(status_code=500, detail=str(e))

async def auto_train_model_background():
    """Background task for automatic model training"""
    try:
        ml_engine = MLEngine()
        model_version = await ml_engine._auto_train_model()
        
        if model_version:
            logger.info(f"Auto-trained model {model_version} successfully in background")
        else:
            logger.error("Automatic model training failed in background task")
            
    except Exception as e:
        logger.error(f"Error in background auto-training: {e}")

@router.get("/health/detailed")
async def detailed_health_check(db: Session = Depends(get_db)):
    """Detailed health check with service status"""
    try:
        # Check database
        db_status = "connected"
        try:
            db.execute("SELECT 1")
        except Exception as e:
            db_status = f"error: {e}"
        
        # Check MCP client
        mcp_client = MCPClient()
        mcp_status = "ready" if await mcp_client.health_check() else "unavailable"
        
        # Check model status
        ml_engine = MLEngine()
        model_status = "ready" if ml_engine.current_model else "no_model"
        
        # Get some basic stats
        total_articles = db.query(Article).count()
        total_buckets = db.query(Bucket).count()
        total_labels = db.query(Label).count()
        
        return {
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat(),
            "services": {
                "database": db_status,
                "mcp_client": mcp_status,
                "ml_engine": model_status
            },
            "stats": {
                "total_articles": total_articles,
                "total_buckets": total_buckets,
                "total_labels": total_labels
            }
        }
        
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# New GeckoTerminal API endpoints
@router.get("/price/{token}")
async def get_token_price(token: str):
    """Get current price and market data for a token"""
    try:
        gecko_client = GeckoTerminalClient()
        price_data = await gecko_client.get_token_price_data(token)
        
        if not price_data:
            raise HTTPException(status_code=404, detail=f"Price data not found for {token}")
        
        return price_data
        
    except Exception as e:
        logger.error(f"Error getting price for {token}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/ohlcv/{token}")
async def get_token_ohlcv(
    token: str,
    timeframe: str = "day",
    limit: int = 30
):
    """Get OHLCV data for a token"""
    try:
        gecko_client = GeckoTerminalClient()
        
        # Get token pool info first
        price_data = await gecko_client.get_token_price_data(token)
        if not price_data:
            raise HTTPException(status_code=404, detail=f"Token {token} not found")
        
        network = price_data["network"]
        pool_address = price_data["pool_address"]
        
        # Get OHLCV data
        ohlcv_data = await gecko_client.get_ohlcv_data(network, pool_address, timeframe, limit)
        
        return {
            "token": token,
            "network": network,
            "pool_address": pool_address,
            "timeframe": timeframe,
            "data": ohlcv_data
        }
        
    except Exception as e:
        logger.error(f"Error getting OHLCV for {token}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/feedback/auto/{token}")
async def auto_submit_feedback(
    token: str,
    background_tasks: BackgroundTasks,
    hours_back: int = 1,
    db: Session = Depends(get_db)
):
    """Automatically submit feedback by calculating actual returns"""
    try:
        background_tasks.add_task(process_auto_feedback, token, hours_back)
        
        return {
            "message": f"Auto feedback collection started for {token}",
            "token": token,
            "hours_back": hours_back,
            "status": "processing"
        }
        
    except Exception as e:
        logger.error(f"Error starting auto feedback for {token}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

async def process_auto_feedback(token: str, hours_back: int):
    """Background task to automatically calculate and submit feedback"""
    try:
        gecko_client = GeckoTerminalClient()
        db = SessionLocal()
        
        try:
            # Get buckets from the specified time period
            since = datetime.utcnow() - timedelta(hours=hours_back)
            buckets = db.query(Bucket).filter(
                Bucket.token == token,
                Bucket.bucket_ts >= since - timedelta(hours=1)  # Get buckets 1 hour before to calculate returns
            ).order_by(Bucket.bucket_ts).all()
            
            feedback_count = 0
            
            for bucket in buckets:
                try:
                    # Check if feedback already exists
                    existing_label = db.query(Label).filter(
                        Label.token == token,
                        Label.bucket_ts == bucket.bucket_ts
                    ).first()
                    
                    if existing_label:
                        continue  # Skip if feedback already exists
                    
                    # Calculate 1-hour return from this bucket timestamp
                    actual_return = await gecko_client.calculate_token_return(token, hours_back=1)
                    
                    if actual_return is not None:
                        # Create label
                        label_binary = 1 if actual_return > 0.005 else 0  # 0.5% threshold
                        
                        new_label = Label(
                            token=token,
                            bucket_ts=bucket.bucket_ts,
                            forward_return_60m=actual_return / 100,  # Convert percentage to decimal
                            label_binary=label_binary
                        )
                        
                        db.add(new_label)
                        feedback_count += 1
                        
                except Exception as e:
                    logger.error(f"Error processing feedback for bucket {bucket.bucket_ts}: {e}")
                    continue
            
            # Commit all feedback
            db.commit()
            logger.info(f"Auto feedback: Created {feedback_count} labels for {token}")
            
        finally:
            db.close()
            
    except Exception as e:
        logger.error(f"Error in auto feedback processing for {token}: {e}")

@router.get("/networks")
async def get_networks():
    """Get available blockchain networks from GeckoTerminal"""
    try:
        gecko_client = GeckoTerminalClient()
        networks = await gecko_client.get_networks()
        
        return {
            "networks": [network.__dict__ for network in networks],
            "count": len(networks)
        }
        
    except Exception as e:
        logger.error(f"Error getting networks: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/tokens/add-mapping")
async def add_token_mapping(
    token: str,
    network: str,
    pools: List[str]
):
    """Add new token pool mapping for price data"""
    try:
        gecko_client = GeckoTerminalClient()
        await gecko_client.add_token_mapping(token, network, pools)
        
        return {
            "message": f"Token mapping added for {token}",
            "token": token,
            "network": network,
            "pools": pools
        }
        
    except Exception as e:
        logger.error(f"Error adding token mapping: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Circuit Breaker and Resilience Management Endpoints
@router.get("/admin/circuit-breakers")
async def get_circuit_breaker_status():
    """Get status of all circuit breakers"""
    try:
        status = {}
        for service_name, breaker in _circuit_breakers.items():
            status[service_name] = {
                "state": breaker.state.state.value,
                "failure_count": breaker.state.failure_count,
                "success_count": breaker.state.success_count,
                "last_failure_time": breaker.state.last_failure_time.isoformat() if breaker.state.last_failure_time else None,
                "next_attempt_time": breaker.state.next_attempt_time.isoformat() if breaker.state.next_attempt_time else None,
                "config": {
                    "failure_threshold": breaker.config.failure_threshold,
                    "timeout": breaker.config.timeout
                }
            }
        
        return {
            "circuit_breakers": status,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error getting circuit breaker status: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/admin/circuit-breakers/{service_name}/reset")
async def reset_circuit_breaker(service_name: str):
    """Manually reset a circuit breaker"""
    try:
        if service_name not in _circuit_breakers:
            raise HTTPException(status_code=404, detail=f"Circuit breaker '{service_name}' not found")
        
        breaker = _circuit_breakers[service_name]
        
        # Reset the circuit breaker state
        from ..utils.resilience import CircuitState, CircuitBreakerState
        breaker.state = CircuitBreakerState(state=CircuitState.CLOSED)
        
        logger.info(f"Circuit breaker '{service_name}' manually reset")
        
        return {
            "message": f"Circuit breaker '{service_name}' has been reset",
            "service": service_name,
            "new_state": "CLOSED",
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error resetting circuit breaker {service_name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/admin/circuit-breakers/reset-all")
async def reset_all_circuit_breakers():
    """Reset all circuit breakers"""
    try:
        reset_count = 0
        from ..utils.resilience import CircuitState, CircuitBreakerState
        
        for service_name, breaker in _circuit_breakers.items():
            old_state = breaker.state.state.value
            breaker.state = CircuitBreakerState(state=CircuitState.CLOSED)
            
            if old_state != "closed":
                logger.info(f"Circuit breaker '{service_name}' reset from {old_state} to CLOSED")
                reset_count += 1
        
        return {
            "message": f"Reset {reset_count} circuit breakers",
            "total_breakers": len(_circuit_breakers),
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error resetting all circuit breakers: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/admin/cache-status")
async def get_cache_status():
    """Get fallback cache status"""
    try:
        cache_info = {
            "cache_size": len(fallback_cache.cache),
            "entries": []
        }
        
        # Get cache entry details
        for key, entry in fallback_cache.cache.items():
            cache_info["entries"].append({
                "key": key,
                "created": entry["created"].isoformat(),
                "expiry": entry["expiry"].isoformat(),
                "expired": datetime.now() > entry["expiry"]
            })
        
        # Sort by creation time (newest first)
        cache_info["entries"] = sorted(
            cache_info["entries"],
            key=lambda x: x["created"],
            reverse=True
        )
        
        return cache_info
        
    except Exception as e:
        logger.error(f"Error getting cache status: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/admin/cache/clear")
async def clear_cache():
    """Clear fallback cache"""
    try:
        cache_size = len(fallback_cache.cache)
        fallback_cache.cache.clear()
        
        logger.info(f"Fallback cache cleared ({cache_size} entries removed)")
        
        return {
            "message": f"Cache cleared successfully",
            "entries_removed": cache_size,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error clearing cache: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/admin/service-health")
async def get_service_health():
    """Get detailed health status of all external services"""
    try:
        services = {}
        
        # Check MCP server
        mcp_client = MCPClient()
        mcp_healthy = await mcp_client.health_check()
        
        services["mcp_server"] = {
            "healthy": mcp_healthy,
            "last_check": datetime.utcnow().isoformat(),
            "url": mcp_client.base_url
        }
        
        # Check GeckoTerminal
        gecko_client = GeckoTerminalClient()
        try:
            networks = await gecko_client.get_networks()
            gecko_healthy = len(networks) > 0
        except:
            gecko_healthy = False
            
        services["gecko_terminal"] = {
            "healthy": gecko_healthy,
            "last_check": datetime.utcnow().isoformat()
        }
        
        # Get all health checker status
        all_status = health_checker.get_all_status()
        services.update(all_status)
        
        return {
            "services": services,
            "overall_healthy": all([s.get("healthy", False) for s in services.values()]),
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error getting service health: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/debug/ingest-sync/{token}")
async def debug_ingest_sync(
    token: str,
    max_articles: int = 3,
    db: Session = Depends(get_db)
):
    """Debug endpoint to test ingestion synchronously with detailed logging"""
    try:
        logger.info(f"Starting synchronous debug ingestion for {token}")
        
        # Initialize services
        mcp_client = MCPClient()
        feature_extractor = FeatureExtractor()
        aggregator = NarrativeAggregator()
        
        # 1. Test MCP connection
        logger.info("Testing MCP server connectivity...")
        search_results = await mcp_client.search(f"{token} token news")
        logger.info(f"Search returned {len(search_results)} results")
        
        if not search_results:
            return {"error": "No search results from MCP server", "token": token}
        
        # 2. Test scraping first result
        test_url = search_results[0].url
        logger.info(f"Testing scrape for: {test_url}")
        scrape_result = await mcp_client.scrape(test_url)
        
        if not scrape_result:
            return {"error": f"Scraping failed for {test_url}", "token": token}
        
        logger.info(f"Scrape successful - content length: {len(scrape_result.content or '')}")
        
        # 3. Test feature extraction
        logger.info("Testing feature extraction...")
        try:
            features = await feature_extractor.extract_features(scrape_result.__dict__, token)
            logger.info(f"Feature extraction successful - sentiment: {features.sentiment_score}, weight: {features.final_weight}")
        except Exception as feat_error:
            logger.error(f"Feature extraction failed: {feat_error}", exc_info=True)
            return {"error": f"Feature extraction failed: {feat_error}", "token": token}
        
        # 4. Test database insertion
        logger.info("Testing database insertion...")
        try:
            # Check if article exists
            existing = db.query(Article).filter(Article.url == scrape_result.url).first()
            if existing:
                logger.info(f"Article already exists in database: {scrape_result.url}")
                return {"message": "Article already exists", "url": scrape_result.url, "token": token}
            
            # Create article
            article = Article(
                token=token,
                url=scrape_result.url,
                site_name=scrape_result.site_name,
                title=scrape_result.title,
                published_at=None,  # Simplified for debug
                clean_content=scrape_result.clean_content,
                word_count=scrape_result.word_count,
                event_probs=features.event_probs,
                sentiment_score=features.sentiment_score,
                source_trust=features.source_trust,
                recency_decay=features.recency_decay,
                novelty_score=features.novelty_score,
                proof_bonus=features.proof_bonus,
                final_weight=features.final_weight
            )
            
            db.add(article)
            db.commit()
            logger.info(f"Article successfully inserted into database")
            
        except Exception as db_error:
            logger.error(f"Database insertion failed: {db_error}", exc_info=True)
            db.rollback()
            return {"error": f"Database insertion failed: {db_error}", "token": token}
        
        # 5. Test aggregation
        logger.info("Testing aggregation...")
        try:
            buckets = await aggregator.process_token_articles(token, 24)
            logger.info(f"Aggregation successful - created {len(buckets)} buckets")
        except Exception as agg_error:
            logger.error(f"Aggregation failed: {agg_error}", exc_info=True)
            return {"error": f"Aggregation failed: {agg_error}", "token": token, "article_created": True}
        
        return {
            "message": "Debug ingestion completed successfully",
            "token": token,
            "search_results": len(search_results),
            "scrape_success": True,
            "feature_extraction_success": True,
            "database_insertion_success": True,
            "aggregation_success": True,
            "buckets_created": len(buckets),
            "article_url": scrape_result.url
        }
        
    except Exception as e:
        logger.error(f"Debug ingestion failed for {token}: {e}", exc_info=True)
        return {"error": f"Debug ingestion failed: {e}", "token": token}

@router.post("/admin/test-mcp")
async def test_mcp_connection():
    """Test MCP server connection and response times"""
    try:
        mcp_client = MCPClient()
        
        # Test search
        start_time = datetime.utcnow()
        search_results = await mcp_client.search("test query")
        search_duration = (datetime.utcnow() - start_time).total_seconds()
        
        # Test scrape (use a reliable URL)
        test_url = "https://www.example.com"
        start_time = datetime.utcnow()
        scrape_result = await mcp_client.scrape(test_url)
        scrape_duration = (datetime.utcnow() - start_time).total_seconds()
        
        return {
            "search_test": {
                "success": len(search_results) >= 0,  # Even empty results are success
                "duration_seconds": search_duration,
                "result_count": len(search_results)
            },
            "scrape_test": {
                "success": scrape_result is not None,
                "duration_seconds": scrape_duration,
                "content_length": len(scrape_result.content or "") if scrape_result else 0
            },
            "overall_status": "operational" if (len(search_results) >= 0 and scrape_result) else "degraded",
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error testing MCP connection: {e}")
        return {
            "search_test": {"success": False, "error": str(e)},
            "scrape_test": {"success": False, "error": str(e)},
            "overall_status": "failed",
            "timestamp": datetime.utcnow().isoformat()
        }

# Universal Token Support Endpoints
@router.post("/tokens/validate")
async def validate_token(token: str):
    """Validate if a token exists and can be analyzed"""
    try:
        gecko_client = GeckoTerminalClient()
        validation_result = await gecko_client.validate_token(token)
        
        return {
            "validation": validation_result,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error validating token {token}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/tokens/discover")
async def discover_token(token: str):
    """Automatically discover token information across networks"""
    try:
        gecko_client = GeckoTerminalClient()
        discovery_result = await gecko_client.discover_token_automatically(token)
        
        if discovery_result:
            return {
                "success": True,
                "token": token.upper(),
                "discovery": discovery_result,
                "message": f"Successfully discovered {token.upper()}",
                "timestamp": datetime.utcnow().isoformat()
            }
        else:
            return {
                "success": False,
                "token": token.upper(),
                "message": f"Could not discover token {token.upper()} in any supported network",
                "suggestion": "Check the token symbol or try alternative networks",
                "timestamp": datetime.utcnow().isoformat()
            }
        
    except Exception as e:
        logger.error(f"Error discovering token {token}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/tokens/search")
async def search_tokens(
    query: str,
    networks: Optional[str] = None,
    limit: int = 10
):
    """Search for tokens across multiple networks"""
    try:
        gecko_client = GeckoTerminalClient()
        
        # Parse networks parameter
        network_list = None
        if networks:
            network_list = [n.strip() for n in networks.split(",")]
        
        search_results = await gecko_client.search_token_pools(query, network_list)
        
        return {
            "query": query,
            "results": search_results[:limit],
            "total_found": len(search_results),
            "networks_searched": network_list or ["eth", "bsc", "polygon", "arbitrum", "solana", "avalanche", "base"],
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error searching tokens with query {query}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/tokens/networks")
async def get_supported_networks():
    """Get list of all supported networks"""
    try:
        gecko_client = GeckoTerminalClient()
        networks = await gecko_client.get_supported_networks()
        
        return {
            "networks": networks,
            "total_networks": len(networks),
            "popular_networks": [n for n in networks if n.get("popular", False)],
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error getting supported networks: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/dashboard/any/{token}")
async def get_universal_dashboard_data(
    token: str,
    hours_back: int = 48,
    auto_discover: bool = True,
    db: Session = Depends(get_db)
):
    """Get dashboard data for ANY token (with auto-discovery)"""
    try:
        token_upper = token.upper()
        
        # First validate/discover the token if auto_discover is enabled
        validation = None
        if auto_discover:
            gecko_client = GeckoTerminalClient()
            validation = await gecko_client.validate_token(token)
            
            if not validation.get("valid", False):
                return {
                    "error": "Token not found or invalid",
                    "token": token_upper,
                    "validation": validation,
                    "suggestion": "Try checking the token symbol or use the /tokens/search endpoint to find it",
                    "timestamp": datetime.utcnow().isoformat()
                }
        
        # Use the existing dashboard logic
        since = datetime.utcnow() - timedelta(hours=hours_back)
        
        # Get buckets
        buckets = db.query(Bucket).filter(
            Bucket.token == token_upper,
            Bucket.bucket_ts >= since
        ).order_by(Bucket.bucket_ts).all()
        
        # If no buckets found, suggest ingestion
        if not buckets:
            return {
                "token": token_upper,
                "message": f"No analysis data found for {token_upper}",
                "suggestion": f"Use POST /api/v1/ingest with token '{token_upper}' to start analysis",
                "auto_discovery": validation if auto_discover else None,
                "current_thesis": {
                    "token": token_upper,
                    "timestamp": datetime.utcnow().isoformat(),
                    "window_minutes": 60,
                    "narrative_heat": 0.0,
                    "consensus": 0.0,
                    "top_event": "unknown",
                    "p_up_60m": 0.5,
                    "confidence": "LOW",
                    "hype_velocity": 0.0,
                    "risk_polarity": 0.0,
                    "reasoning": [f"No analysis data available for {token_upper} - ingest data first"],
                    "guardrails": ["Token discovered but needs data ingestion"],
                    "evidence": [],
                    "features_snapshot": {}
                },
                "buckets": [],
                "recent_articles": [],
                "summary": {
                    "total_buckets": 0,
                    "avg_narrative_heat": 0.0,
                    "latest_consensus": 0.0,
                    "latest_risk_polarity": 0.0
                },
                "token_info": validation if auto_discover else None
            }
        
        # Continue with normal dashboard logic
        latest_bucket = buckets[-1]
        ml_engine = MLEngine()
        bucket_data = latest_bucket.to_dict()
        prediction = await ml_engine.predict(bucket_data)
        
        thesis_composer = ThesisComposer()
        thesis = await thesis_composer.compose_thesis(
            token_upper, bucket_data, prediction, 60
        )
        
        # Get recent articles
        recent_articles = db.query(Article).filter(
            Article.token == token_upper,
            Article.created_at >= since - timedelta(hours=6)
        ).order_by(Article.final_weight.desc()).limit(10).all()
        
        return {
            "token": token_upper,
            "auto_discovered": auto_discover and validation and validation.get("source") == "auto_discovery",
            "token_info": validation if auto_discover else None,
            "current_thesis": thesis_composer.to_dict(thesis),
            "buckets": [bucket.to_dict() for bucket in buckets],
            "recent_articles": [
                {
                    "title": article.title,
                    "url": article.url,
                    "site_name": article.site_name,
                    "sentiment_score": article.sentiment_score,
                    "final_weight": article.final_weight,
                    "event_probs": article.event_probs,
                    "created_at": article.created_at.isoformat() if article.created_at else None
                }
                for article in recent_articles
            ],
            "summary": {
                "total_buckets": len(buckets),
                "avg_narrative_heat": sum(b.narrative_heat or 0 for b in buckets) / len(buckets),
                "latest_consensus": latest_bucket.consensus,
                "latest_risk_polarity": latest_bucket.risk_polarity
            }
        }
        
    except Exception as e:
        logger.error(f"Error getting universal dashboard data for {token}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Comprehensive Monitoring and Logging Endpoints
@router.get("/monitoring/metrics")
async def get_monitoring_metrics():
    """Get comprehensive system metrics and monitoring data"""
    try:
        from ..utils.monitoring import metrics_collector, performance_monitor, alert_manager
        
        # Get system metrics
        metrics_summary = metrics_collector.get_metrics_summary()
        active_requests = performance_monitor.get_active_requests()
        active_alerts = alert_manager.get_active_alerts()
        
        # Get system resources
        import psutil
        system_info = {
            "cpu_percent": psutil.cpu_percent(interval=1),
            "memory": {
                "total_gb": psutil.virtual_memory().total / (1024**3),
                "available_gb": psutil.virtual_memory().available / (1024**3),
                "percent_used": psutil.virtual_memory().percent
            },
            "disk": {
                "total_gb": psutil.disk_usage('/').total / (1024**3),
                "free_gb": psutil.disk_usage('/').free / (1024**3),
                "percent_used": psutil.disk_usage('/').percent
            }
        }
        
        return {
            "metrics_summary": metrics_summary,
            "active_requests": active_requests,
            "active_alerts": active_alerts,
            "system_resources": system_info,
            "monitoring_status": "healthy",
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error getting monitoring metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/monitoring/logs/recent")
async def get_recent_logs(
    limit: int = 100,
    level: Optional[str] = None,
    service: Optional[str] = None
):
    """Get recent structured logs with filtering"""
    try:
        # This would typically read from a log aggregation system
        # For now, return a placeholder response
        return {
            "message": "Recent logs endpoint - integrate with log aggregation system",
            "filters": {
                "limit": limit,
                "level": level,
                "service": service
            },
            "suggestion": "Integrate with ELK Stack, Grafana Loki, or similar log aggregation system",
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error getting recent logs: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/monitoring/alerts/acknowledge")
async def acknowledge_alert(alert_name: str):
    """Acknowledge an active alert"""
    try:
        from ..utils.monitoring import alert_manager
        
        if alert_name in alert_manager.active_alerts:
            alert_manager.active_alerts.pop(alert_name)
            logger.info(f"Alert acknowledged: {alert_name}")
            
            return {
                "message": f"Alert '{alert_name}' acknowledged and cleared",
                "alert_name": alert_name,
                "timestamp": datetime.utcnow().isoformat()
            }
        else:
            raise HTTPException(status_code=404, detail=f"Alert '{alert_name}' not found")
            
    except Exception as e:
        logger.error(f"Error acknowledging alert: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/monitoring/health/comprehensive")
async def comprehensive_health_check():
    """Comprehensive health check with detailed service status"""
    try:
        from ..utils.monitoring import metrics_collector
        
        # Check all services
        health_status = {
            "overall_status": "healthy",
            "checks": {},
            "metrics": {},
            "timestamp": datetime.utcnow().isoformat()
        }
        
        # Database health
        try:
            db = SessionLocal()
            db.execute("SELECT 1")
            db.close()
            health_status["checks"]["database"] = {"status": "healthy", "response_time_ms": 0}
        except Exception as e:
            health_status["checks"]["database"] = {"status": "unhealthy", "error": str(e)}
            health_status["overall_status"] = "degraded"
        
        # MCP Client health
        try:
            mcp_client = MCPClient()
            mcp_healthy = await mcp_client.health_check()
            health_status["checks"]["mcp_client"] = {
                "status": "healthy" if mcp_healthy else "unhealthy",
                "response_time_ms": 0
            }
            if not mcp_healthy:
                health_status["overall_status"] = "degraded"
        except Exception as e:
            health_status["checks"]["mcp_client"] = {"status": "unhealthy", "error": str(e)}
            health_status["overall_status"] = "degraded"
        
        # ML Engine health
        try:
            ml_engine = MLEngine()
            model_status = await ml_engine.get_model_status()
            health_status["checks"]["ml_engine"] = {
                "status": "healthy" if model_status.get("has_active_model", False) else "warning",
                "has_model": model_status.get("has_active_model", False),
                "model_version": model_status.get("model_version"),
                "labeled_samples": model_status.get("labeled_samples", 0)
            }
        except Exception as e:
            health_status["checks"]["ml_engine"] = {"status": "unhealthy", "error": str(e)}
            health_status["overall_status"] = "degraded"
        
        # Groq API health (check circuit breaker status)
        try:
            from ..utils.resilience import _circuit_breakers
            groq_breaker = _circuit_breakers.get("groq_api")
            if groq_breaker:
                breaker_state = groq_breaker.state.state.value
                health_status["checks"]["groq_api"] = {
                    "status": "healthy" if breaker_state == "closed" else "degraded",
                    "circuit_breaker_state": breaker_state,
                    "failure_count": groq_breaker.state.failure_count
                }
                if breaker_state != "closed":
                    health_status["overall_status"] = "degraded"
            else:
                health_status["checks"]["groq_api"] = {"status": "unknown", "message": "Circuit breaker not initialized"}
        except Exception as e:
            health_status["checks"]["groq_api"] = {"status": "unhealthy", "error": str(e)}
        
        # Add metrics summary
        health_status["metrics"] = metrics_collector.get_metrics_summary()
        
        return health_status
        
    except Exception as e:
        logger.error(f"Error in comprehensive health check: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/monitoring/performance/report")
async def get_performance_report(hours_back: int = 24):
    """Get detailed performance report"""
    try:
        from ..utils.monitoring import metrics_collector, performance_monitor
        
        # Get performance metrics
        metrics_summary = metrics_collector.get_metrics_summary()
        active_requests = performance_monitor.get_active_requests()
        
        # Calculate performance stats
        request_metrics = [m for m in metrics_collector.metrics_data if m.name == "request"]
        api_call_metrics = [m for m in metrics_collector.metrics_data if m.name == "api_call"]
        
        performance_stats = {
            "requests": {
                "total_requests": len(request_metrics),
                "avg_response_time": sum(m.value for m in request_metrics) / len(request_metrics) if request_metrics else 0,
                "active_requests": len(active_requests),
                "error_rate": len([m for m in request_metrics if m.labels.get("status_code", "").startswith("5")]) / len(request_metrics) if request_metrics else 0
            },
            "api_calls": {
                "total_calls": len(api_call_metrics),
                "success_rate": len([m for m in api_call_metrics if m.labels.get("status") == "success"]) / len(api_call_metrics) if api_call_metrics else 0,
                "services": list(set(m.labels.get("service", "unknown") for m in api_call_metrics))
            },
            "system_performance": {
                "cpu_usage": psutil.cpu_percent(interval=1),
                "memory_usage": psutil.virtual_memory().percent,
                "disk_usage": psutil.disk_usage('/').percent
            },
            "period": f"Last {hours_back} hours",
            "timestamp": datetime.utcnow().isoformat()
        }
        
        return performance_stats
        
    except Exception as e:
        logger.error(f"Error generating performance report: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# =============================================================================
# ADMIN TOKEN MANAGEMENT ENDPOINTS
# =============================================================================

@router.post("/admin/tokens", response_model=TrackedTokenResponse)
async def create_tracked_token(
    token_data: TrackedTokenCreate,
    db: Session = Depends(get_db)
):
    """
    Create a new tracked token for automated analysis
    
    This endpoint allows admins to add tokens to the tracking system
    for automated monitoring and analysis.
    """
    try:
        # Validate symbol format
        symbol = token_data.symbol.upper().strip()
        if not symbol or len(symbol) > 20:
            raise HTTPException(status_code=400, detail="Invalid token symbol")
        
        # Check if token already exists
        existing_token = db.query(TrackedToken).filter(
            TrackedToken.symbol == symbol
        ).first()
        
        if existing_token:
            raise HTTPException(
                status_code=409, 
                detail=f"Token {symbol} is already being tracked"
            )
        
        # Validate chain_id if provided
        if token_data.chain_id is not None:
            valid_chains = [1, 56, 137, 250, 42161, 10, 8453, 43114, 43113]  # Added Fuji testnet
            if token_data.chain_id not in valid_chains:
                raise HTTPException(
                    status_code=400, 
                    detail=f"Unsupported chain_id. Must be one of: {valid_chains}"
                )
        
        # Create new tracked token
        tracked_token = TrackedToken(
            symbol=symbol,
            name=token_data.name,
            chain_id=token_data.chain_id,
            contract_address=token_data.contract_address,
            gecko_id=token_data.gecko_id,
            auto_analysis=token_data.auto_analysis,
            analysis_interval_hours=token_data.analysis_interval_hours,
            added_by=token_data.added_by,
            token_metadata=token_data.metadata or {}
        )
        
        db.add(tracked_token)
        db.commit()
        db.refresh(tracked_token)
        
        logger.info(f"Created tracked token: {symbol} (ID: {tracked_token.id})")
        
        return TrackedTokenResponse(**tracked_token.to_dict())
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating tracked token: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/admin/tokens", response_model=List[TrackedTokenResponse])
async def list_tracked_tokens(
    active_only: bool = True,
    db: Session = Depends(get_db)
):
    """
    List all tracked tokens
    
    Query parameters:
    - active_only: If true, only return active tokens (default: true)
    """
    try:
        query = db.query(TrackedToken)
        
        if active_only:
            query = query.filter(TrackedToken.is_active)
        
        tokens = query.order_by(TrackedToken.created_at.desc()).all()
        
        return [TrackedTokenResponse(**token.to_dict()) for token in tokens]
        
    except Exception as e:
        logger.error(f"Error listing tracked tokens: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/admin/tokens/{symbol}", response_model=TrackedTokenResponse)
async def get_tracked_token(
    symbol: str,
    db: Session = Depends(get_db)
):
    """Get details of a specific tracked token"""
    try:
        symbol = symbol.upper().strip()
        
        token = db.query(TrackedToken).filter(
            TrackedToken.symbol == symbol
        ).first()
        
        if not token:
            raise HTTPException(status_code=404, detail=f"Token {symbol} not found")
        
        return TrackedTokenResponse(**token.to_dict())
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting tracked token {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/admin/tokens/{symbol}", response_model=TrackedTokenResponse)
async def update_tracked_token(
    symbol: str,
    token_data: TrackedTokenUpdate,
    db: Session = Depends(get_db)
):
    """Update an existing tracked token"""
    try:
        symbol = symbol.upper().strip()
        
        token = db.query(TrackedToken).filter(
            TrackedToken.symbol == symbol
        ).first()
        
        if not token:
            raise HTTPException(status_code=404, detail=f"Token {symbol} not found")
        
        # Update fields if provided
        update_data = token_data.dict(exclude_unset=True)
        for field, value in update_data.items():
            if hasattr(token, field):
                setattr(token, field, value)
        
        # Validate chain_id if being updated
        if token_data.chain_id is not None:
            valid_chains = [1, 56, 137, 250, 42161, 10, 8453, 43114, 43113]  # Added Fuji testnet
            if token_data.chain_id not in valid_chains:
                raise HTTPException(
                    status_code=400, 
                    detail=f"Unsupported chain_id. Must be one of: {valid_chains}"
                )
        
        db.commit()
        db.refresh(token)
        
        logger.info(f"Updated tracked token: {symbol}")
        
        return TrackedTokenResponse(**token.to_dict())
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating tracked token {symbol}: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/admin/tokens/{symbol}")
async def delete_tracked_token(
    symbol: str,
    hard_delete: bool = False,
    db: Session = Depends(get_db)
):
    """
    Delete a tracked token
    
    Query parameters:
    - hard_delete: If true, permanently delete from database. 
                  If false, just mark as inactive (default: false)
    """
    try:
        symbol = symbol.upper().strip()
        
        token = db.query(TrackedToken).filter(
            TrackedToken.symbol == symbol
        ).first()
        
        if not token:
            raise HTTPException(status_code=404, detail=f"Token {symbol} not found")
        
        if hard_delete:
            db.delete(token)
            logger.info(f"Hard deleted tracked token: {symbol}")
            message = f"Token {symbol} permanently deleted"
        else:
            token.is_active = False
            logger.info(f"Soft deleted tracked token: {symbol}")
            message = f"Token {symbol} marked as inactive"
        
        db.commit()
        
        return {"message": message, "symbol": symbol, "hard_delete": hard_delete}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting tracked token {symbol}: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/admin/tokens/{symbol}/analyze")
async def trigger_token_analysis(
    symbol: str,
    background_tasks: BackgroundTasks,
    hours_back: int = 24,
    max_articles: int = 20,
    db: Session = Depends(get_db)
):
    """
    Manually trigger analysis for a tracked token
    
    This endpoint allows admins to force analysis of a tracked token
    outside of its normal schedule.
    """
    try:
        symbol = symbol.upper().strip()
        
        # Check if token is tracked
        token = db.query(TrackedToken).filter(
            TrackedToken.symbol == symbol,
            TrackedToken.is_active
        ).first()
        
        if not token:
            raise HTTPException(
                status_code=404, 
                detail=f"Active tracked token {symbol} not found"
            )
        
        # Update last analysis timestamp
        token.last_analysis_at = datetime.utcnow()
        db.commit()
        
        # Trigger the analysis (reuse existing ingestion logic)
        background_tasks.add_task(
            process_token_ingestion,
            symbol,
            hours_back,
            max_articles
        )
        
        # Initialize status tracking
        update_ingestion_status(
            symbol, 
            "starting", 
            f"Manual analysis triggered for tracked token {symbol}", 
            progress=5,
            started_at=datetime.utcnow().isoformat(),
            articles_processed=0,
            articles_total=max_articles
        )
        
        logger.info(f"Manual analysis triggered for tracked token: {symbol}")
        
        return {
            "message": f"Analysis started for tracked token {symbol}",
            "symbol": symbol,
            "hours_back": hours_back,
            "max_articles": max_articles,
            "status": "processing"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error triggering analysis for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ================================
# DEPOSIT SYSTEM ENDPOINTS
# ================================

# Initialize deposit service
deposit_service = DepositService()

@router.get("/deposit/chains", response_model=List[SupportedChainResponse])
async def get_supported_chains():
    """Get list of supported blockchain networks for deposits"""
    try:
        chains = await deposit_service.get_supported_chains()
        return [
            SupportedChainResponse(
                chain_id=chain["chainId"],
                name=chain["name"],
                native_currency=chain["nativeCurrency"]
            )
            for chain in chains
        ]
    except Exception as e:
        logger.error(f"Error fetching supported chains: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch supported chains")

@router.get("/deposit/managed-wallets", response_model=List[ManagedWalletResponse])
async def get_managed_wallets():
    """Get AgentChain managed wallet addresses for all chains"""
    try:
        addresses = await deposit_service.get_managed_wallet_addresses()
        return [
            ManagedWalletResponse(
                chain_id=addr["chainId"],
                chain_name=addr["chainName"],
                smart_account=addr["smartAccount"],
                eoa_address=addr["eoaAddress"]
            )
            for addr in addresses
            if "error" not in addr
        ]
    except Exception as e:
        logger.error(f"Error fetching managed wallet addresses: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch managed wallet addresses")

@router.post("/deposit/address", response_model=DepositAddressResponse)
async def get_deposit_address(request: DepositAddressRequest, db: Session = Depends(get_db)):
    """Get deposit address for a user on a specific chain"""
    try:
        # Validate chain is supported
        supported_chains = await deposit_service.get_supported_chains()
        chain_ids = [chain["chainId"] for chain in supported_chains]
        
        if request.chain_id not in chain_ids:
            raise HTTPException(
                status_code=400, 
                detail=f"Unsupported chain ID: {request.chain_id}. Supported: {chain_ids}"
            )
        
        # Check if the requested chain is actually supported by the microservice
        managed_wallets = await deposit_service.get_managed_wallet_addresses()
        managed_wallet = next(
            (wallet for wallet in managed_wallets if wallet["chainId"] == request.chain_id),
            None
        )
        
        # Check if this chain is active in the microservice
        if managed_wallet and not managed_wallet.get("isActive", True):
            raise HTTPException(
                status_code=400, 
                detail=f"Chain {request.chain_id} is not currently supported by the microservice. The microservice is configured for chain 43114 (Avalanche mainnet). Please switch to that network or reconfigure the microservice for Fuji testnet."
            )
        
        # Get deposit address
        deposit_address = deposit_service.get_user_deposit_address(
            db, request.user_wallet_address, request.chain_id
        )
        
        if not deposit_address:
            raise HTTPException(status_code=404, detail="No managed wallet available for this chain")
        
        # Get chain info
        chain_info = next(
            (chain for chain in supported_chains if chain["chainId"] == request.chain_id),
            None
        )
        
        return DepositAddressResponse(
            user_wallet_address=request.user_wallet_address,
            chain_id=request.chain_id,
            chain_name=chain_info["name"] if chain_info else "Unknown",
            deposit_address=deposit_address,
            smart_account=managed_wallet["smartAccount"] if managed_wallet else deposit_address,
            eoa_address=managed_wallet["eoaAddress"] if managed_wallet else ""
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting deposit address: {e}")
        raise HTTPException(status_code=500, detail="Failed to get deposit address")

@router.post("/deposit/record")
async def record_deposit(request: RecordDepositRequest, db: Session = Depends(get_db)):
    """Record a user deposit transaction"""
    try:
        # Validate inputs
        if not request.user_wallet_address or not request.tx_hash:
            raise HTTPException(status_code=400, detail="Missing required fields")
        
        if float(request.amount) <= 0:
            raise HTTPException(status_code=400, detail="Amount must be positive")
        
        # Record the deposit
        deposit = deposit_service.record_deposit(
            db,
            request.user_wallet_address,
            request.chain_id,
            request.token_symbol,
            request.amount,
            request.tx_hash
        )
        
        return {
            "success": True,
            "deposit_id": deposit.id,
            "message": "Deposit recorded successfully",
            "status": deposit.status,
            "tx_hash": deposit.transaction_hash
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error recording deposit: {e}")
        raise HTTPException(status_code=500, detail="Failed to record deposit")

@router.put("/deposit/status")
async def update_deposit_status(request: DepositStatusUpdate, db: Session = Depends(get_db)):
    """Update the status of a deposit transaction"""
    try:
        if request.status not in ["pending", "confirmed", "failed"]:
            raise HTTPException(status_code=400, detail="Invalid status. Must be: pending, confirmed, failed")
        
        confirmed_at = datetime.utcnow() if request.status == "confirmed" else None
        
        deposit = deposit_service.update_deposit_status(
            db, request.tx_hash, request.status, confirmed_at
        )
        
        if not deposit:
            raise HTTPException(status_code=404, detail="Deposit not found")
        
        return {
            "success": True,
            "deposit_id": deposit.id,
            "status": deposit.status,
            "confirmed_at": deposit.confirmed_at.isoformat() if deposit.confirmed_at else None
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating deposit status: {e}")
        raise HTTPException(status_code=500, detail="Failed to update deposit status")

@router.get("/deposit/balances/{user_wallet_address}", response_model=List[UserBalanceResponse])
async def get_user_balances(user_wallet_address: str, db: Session = Depends(get_db)):
    """Get all balances for a user across all chains"""
    try:
        balances = deposit_service.get_user_balances(db, user_wallet_address)
        
        return [
            UserBalanceResponse(
                chain_id=balance["chain_id"],
                chain_name=balance["chain_name"],
                token_symbol=balance["token_symbol"],
                balance=balance["balance"],
                updated_at=balance["updated_at"]
            )
            for balance in balances
        ]
        
    except Exception as e:
        logger.error(f"Error getting user balances: {e}")
        raise HTTPException(status_code=500, detail="Failed to get user balances")

@router.post("/deposit/initialize")
async def initialize_managed_wallets(db: Session = Depends(get_db)):
    """Initialize managed wallet records in database (admin endpoint)"""
    try:
        await deposit_service.initialize_managed_wallets_async(db)
        
        return {
            "success": True,
            "message": "Managed wallets initialized successfully"
        }
        
    except Exception as e:
        logger.error(f"Error initializing managed wallets: {e}")
        raise HTTPException(status_code=500, detail="Failed to initialize managed wallets")

@router.get("/deposit/health")
async def deposit_system_health():
    """Check health of deposit system and microservice connectivity"""
    try:
        # Test microservice connectivity
        chains = await deposit_service.get_supported_chains()
        addresses = await deposit_service.get_managed_wallet_addresses()
        
        # Count successful address fetches
        successful_chains = len([addr for addr in addresses if "error" not in addr])
        total_chains = len(chains)
        
        return {
            "success": True,
            "microservice_connected": True,
            "total_chains": total_chains,
            "active_chains": successful_chains,
            "chains": chains,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Deposit system health check failed: {e}")
        return {
            "success": False,
            "microservice_connected": False,
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }

# Portfolio Management Endpoints

@router.get("/portfolio/status/{user_address}")
async def get_portfolio_status(user_address: str, db: Session = Depends(get_db)):
    """Get current portfolio status for a user"""
    try:
        # Get portfolio tracking info
        portfolio = await portfolio_service.get_portfolio(user_address, db)
        
        if not portfolio:
            return {
                "user_address": user_address,
                "status": "no_portfolio",
                "total_value_usd": 0,
                "positions": [],
                "last_rebalance": None,
                "performance": {
                    "total_return": 0,
                    "daily_return": 0,
                    "trades_count": 0
                }
            }
        
        return {
            "user_address": user_address,
            "status": "active",
            "total_value_usd": portfolio.get("total_value_usd", 0),
            "positions": portfolio.get("positions", []),
            "last_rebalance": portfolio.get("last_rebalance"),
            "performance": portfolio.get("performance", {}),
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to get portfolio status: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get portfolio status: {str(e)}")

@router.post("/portfolio/rebalance")
async def trigger_portfolio_rebalance(request: RebalanceRequest, db: Session = Depends(get_db)):
    """Trigger portfolio rebalancing for a user"""
    try:
        # Get current portfolio
        portfolio = await portfolio_service.get_portfolio(request.user_address, db)
        if not portfolio:
            raise HTTPException(status_code=404, detail="Portfolio not found")
        
        # Generate rebalancing trades
        trades = await portfolio_service.generate_rebalancing_trades(request.user_address, db)
        
        if not trades:
            return {
                "status": "no_rebalance_needed",
                "message": "Portfolio is already optimally allocated",
                "trades": [],
                "timestamp": datetime.utcnow().isoformat()
            }
        
        # Execute trades (in production this would integrate with 0xgasless)
        execution_results = []
        for trade in trades:
            # For now, simulate trade execution
            result = {
                "token": trade["token"],
                "action": trade["action"],
                "amount": trade["amount"],
                "expected_usd": trade["expected_usd"],
                "status": "simulated",  # In production: "executed" or "failed"
                "tx_hash": f"0x{trade['token'][:8]}...simulated"
            }
            execution_results.append(result)
        
        # Record rebalance
        await portfolio_service.record_rebalance(request.user_address, trades, db)
        
        return {
            "status": "rebalanced",
            "trades_executed": len(execution_results),
            "trades": execution_results,
            "total_value_moved": sum(t["expected_usd"] for t in trades),
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to rebalance portfolio: {e}")
        raise HTTPException(status_code=500, detail=f"Rebalancing failed: {str(e)}")

@router.get("/portfolio/predictions/{user_address}")
async def get_portfolio_predictions(user_address: str, db: Session = Depends(get_db)):
    """Get ML predictions for user's portfolio tokens"""
    try:
        # Get user's current positions
        portfolio = await portfolio_service.get_portfolio(user_address, db)
        if not portfolio:
            raise HTTPException(status_code=404, detail="Portfolio not found")
        
        # Get predictions for each token in portfolio
        predictions = {}
        for position in portfolio.get("positions", []):
            token = position["token"]
            try:
                prediction = await portfolio_service.get_token_prediction(token, db)
                predictions[token] = {
                    "current_position": position,
                    "prediction": prediction,
                    "recommendation": "hold"  # Default recommendation
                }
                
                # Simple recommendation logic
                if prediction and prediction.get("prediction_score", 0) > 0.7:
                    predictions[token]["recommendation"] = "increase"
                elif prediction and prediction.get("prediction_score", 0) < 0.3:
                    predictions[token]["recommendation"] = "decrease"
                    
            except Exception as e:
                logger.warning(f"Failed to get prediction for {token}: {e}")
                predictions[token] = {
                    "current_position": position,
                    "prediction": None,
                    "recommendation": "hold",
                    "error": str(e)
                }
        
        return {
            "user_address": user_address,
            "predictions": predictions,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to get portfolio predictions: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get predictions: {str(e)}")

@router.get("/portfolio/performance/{user_address}")
async def get_portfolio_performance(user_address: str, days: int = 30, db: Session = Depends(get_db)):
    """Get portfolio performance metrics over time"""
    try:
        performance = await portfolio_service.get_performance_metrics(user_address, days, db)
        
        return {
            "user_address": user_address,
            "period_days": days,
            "performance": performance,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to get portfolio performance: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get performance: {str(e)}")

@router.post("/portfolio/auto-trade/toggle")
async def toggle_auto_trading(request: PortfolioRequest, enable: bool = True, db: Session = Depends(get_db)):
    """Enable or disable automatic trading for a user"""
    try:
        # Update user's auto-trading preference
        result = await portfolio_service.set_auto_trading(request.user_address, enable, db)
        
        return {
            "user_address": request.user_address,
            "auto_trading_enabled": enable,
            "status": "updated" if result else "failed",
            "message": f"Auto-trading {'enabled' if enable else 'disabled'} for user",
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to toggle auto-trading: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update auto-trading: {str(e)}")

@router.get("/portfolio/trades/{user_address}")
async def get_trade_history(user_address: str, limit: int = 50, db: Session = Depends(get_db)):
    """Get trade history for a user"""
    try:
        trades = await portfolio_service.get_trade_history(user_address, limit, db)
        
        return {
            "user_address": user_address,
            "trades": trades,
            "total_trades": len(trades),
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to get trade history: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get trade history: {str(e)}")

@router.get("/portfolio/analytics")
async def get_portfolio_analytics(db: Session = Depends(get_db)):
    """Get system-wide portfolio analytics"""
    try:
        analytics = await portfolio_service.get_system_analytics(db)
        
        return {
            "analytics": analytics,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to get portfolio analytics: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get analytics: {str(e)}")

# Automated Trading Scheduler Endpoints

@router.get("/scheduler/status")
async def get_scheduler_status():
    """Get automated trading scheduler status"""
    try:
        scheduler = get_trading_scheduler()
        status = await scheduler.get_scheduler_status()
        
        return {
            "scheduler": status,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to get scheduler status: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get scheduler status: {str(e)}")

@router.post("/scheduler/start")
async def start_scheduler():
    """Start the automated trading scheduler"""
    try:
        scheduler = get_trading_scheduler()
        
        if scheduler.is_running:
            return {
                "status": "already_running",
                "message": "Scheduler is already running",
                "timestamp": datetime.utcnow().isoformat()
            }
        
        # Start scheduler in background task
        import asyncio
        asyncio.create_task(scheduler.start_scheduler())
        
        return {
            "status": "started",
            "message": "Automated trading scheduler started",
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to start scheduler: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to start scheduler: {str(e)}")

@router.post("/scheduler/stop")
async def stop_scheduler():
    """Stop the automated trading scheduler"""
    try:
        scheduler = get_trading_scheduler()
        await scheduler.stop_scheduler()
        
        return {
            "status": "stopped",
            "message": "Automated trading scheduler stopped",
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to stop scheduler: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to stop scheduler: {str(e)}")