from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import logging
from pathlib import Path

# Setup logger
logger = logging.getLogger(__name__)

# Create data directory if it doesn't exist
DATA_DIR = Path(__file__).parent.parent.parent / "data"
DATA_DIR.mkdir(exist_ok=True)

# SQLite database URL
DATABASE_URL = f"sqlite:///{DATA_DIR}/ntm_trading.db"

# Create engine with connection pooling for SQLite
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},  # Needed for SQLite
    echo=False  # Set to True for SQL logging
)

# Create SessionLocal class
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create Base class for models
Base = declarative_base()

# Dependency to get DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Database initialization
def init_db():
    """Initialize database tables"""
    Base.metadata.create_all(bind=engine)

def seed_default_tokens():
    """Seed database with top 10 crypto tokens for tracking"""
    from .models import TrackedToken
    
    # Top 10 crypto tokens by market cap (as of 2024/2025)
    default_tokens = [
        {
            "symbol": "BTC",
            "name": "Bitcoin", 
            "chain_id": 1,  # Ethereum (wrapped BTC)
            "gecko_id": "bitcoin",
            "auto_analysis": True,
            "analysis_interval_hours": 6,
            "added_by": "system",
            "token_metadata": {"tier": "tier1", "category": "store_of_value"}
        },
        {
            "symbol": "ETH",
            "name": "Ethereum",
            "chain_id": 1,
            "gecko_id": "ethereum", 
            "auto_analysis": True,
            "analysis_interval_hours": 6,
            "added_by": "system",
            "token_metadata": {"tier": "tier1", "category": "smart_contract_platform"}
        },
        {
            "symbol": "SOL",
            "name": "Solana",
            "chain_id": 1,  # Wrapped on Ethereum
            "gecko_id": "solana",
            "auto_analysis": True,
            "analysis_interval_hours": 6,
            "added_by": "system", 
            "token_metadata": {"tier": "tier1", "category": "smart_contract_platform"}
        },
        {
            "symbol": "BNB",
            "name": "BNB",
            "chain_id": 56,  # BSC native
            "gecko_id": "binancecoin",
            "auto_analysis": True,
            "analysis_interval_hours": 8,
            "added_by": "system",
            "token_metadata": {"tier": "tier1", "category": "exchange_token"}
        },
        {
            "symbol": "ADA",
            "name": "Cardano",
            "chain_id": 1,  # Wrapped on Ethereum
            "gecko_id": "cardano",
            "auto_analysis": True,
            "analysis_interval_hours": 8,
            "added_by": "system",
            "token_metadata": {"tier": "tier1", "category": "smart_contract_platform"}
        },
        {
            "symbol": "AVAX",
            "name": "Avalanche",
            "chain_id": 43114,  # Avalanche native
            "gecko_id": "avalanche-2",
            "auto_analysis": True,
            "analysis_interval_hours": 8,
            "added_by": "system",
            "token_metadata": {"tier": "tier1", "category": "smart_contract_platform"}
        },
        {
            "symbol": "MATIC",
            "name": "Polygon",
            "chain_id": 137,  # Polygon native
            "gecko_id": "matic-network",
            "auto_analysis": True,
            "analysis_interval_hours": 8,
            "added_by": "system",
            "token_metadata": {"tier": "tier2", "category": "layer2_scaling"}
        },
        {
            "symbol": "DOT",
            "name": "Polkadot",
            "chain_id": 1,  # Wrapped on Ethereum
            "gecko_id": "polkadot",
            "auto_analysis": True,
            "analysis_interval_hours": 12,
            "added_by": "system",
            "token_metadata": {"tier": "tier2", "category": "interoperability"}
        },
        {
            "symbol": "LINK",
            "name": "Chainlink",
            "chain_id": 1,  # Ethereum native
            "contract_address": "0x514910771AF9Ca656af840dff83E8264EcF986CA",
            "gecko_id": "chainlink", 
            "auto_analysis": True,
            "analysis_interval_hours": 12,
            "added_by": "system",
            "token_metadata": {"tier": "tier2", "category": "oracle_network"}
        },
        {
            "symbol": "UNI",
            "name": "Uniswap",
            "chain_id": 1,  # Ethereum native
            "contract_address": "0x1f9840a85d5aF5bf1D1762F925BDADdC4201F984",
            "gecko_id": "uniswap",
            "auto_analysis": True, 
            "analysis_interval_hours": 12,
            "added_by": "system",
            "token_metadata": {"tier": "tier2", "category": "decentralized_exchange"}
        }
    ]
    
    db = SessionLocal()
    try:
        # Check if tokens already exist to avoid duplicates
        existing_count = db.query(TrackedToken).filter(
            TrackedToken.added_by == "system"
        ).count()
        
        if existing_count > 0:
            logger.info(f"Default tokens already seeded ({existing_count} system tokens found)")
            return
        
        # Add default tokens
        tokens_added = 0
        for token_data in default_tokens:
            # Check if token already exists by symbol
            existing = db.query(TrackedToken).filter(
                TrackedToken.symbol == token_data["symbol"]
            ).first()
            
            if not existing:
                token = TrackedToken(**token_data)
                db.add(token)
                tokens_added += 1
        
        db.commit()
        logger.info(f"Successfully seeded {tokens_added} default tokens for tracking")
        
    except Exception as e:
        logger.error(f"Error seeding default tokens: {e}")
        db.rollback()
    finally:
        db.close()

def get_engine():
    """Get database engine"""
    return engine

def seed_managed_wallets():
    """Initialize managed wallet records from 0xgasless microservice"""
    from .services.deposit_service import DepositService
    
    db = SessionLocal()
    try:
        # Check if managed wallets already exist
        from .models import ManagedWallet
        existing_count = db.query(ManagedWallet).count()
        
        if existing_count > 0:
            logger.info(f"Managed wallets already initialized ({existing_count} wallets found)")
            return
        
        # Initialize managed wallets from microservice
        deposit_service = DepositService()
        deposit_service.initialize_managed_wallets(db)
        
        logger.info("Successfully initialized managed wallets from microservice")
        
    except Exception as e:
        logger.error(f"Error initializing managed wallets: {e}")
        # Don't raise exception - this is optional during startup
    finally:
        db.close()