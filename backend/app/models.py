from sqlalchemy import Column, Integer, String, DateTime, Text, Float, JSON, Boolean, UniqueConstraint, ForeignKey, DECIMAL
from sqlalchemy.orm import relationship, backref
from sqlalchemy.sql import func
from .database import Base
from datetime import datetime
from typing import Dict, Any, Optional

class Article(Base):
    __tablename__ = "articles"
    
    id = Column(Integer, primary_key=True, index=True)
    token = Column(String(20), index=True, nullable=False)
    url = Column(Text, unique=True, nullable=False)
    site_name = Column(String(100), nullable=True)
    title = Column(Text, nullable=True)
    published_at = Column(DateTime, nullable=True)
    clean_content = Column(Text, nullable=True)
    word_count = Column(Integer, nullable=True)
    
    # Feature extraction results
    event_probs = Column(JSON, nullable=True)  # {"listing": 0.8, "partnership": 0.2, ...}
    sentiment_score = Column(Float, nullable=True)  # [-1, 1]
    source_trust = Column(Float, nullable=True)     # [0.5, 1.2]
    recency_decay = Column(Float, nullable=True)    # exp(-Δt/τ)
    novelty_score = Column(Float, nullable=True)    # [0, 1]
    proof_bonus = Column(Float, nullable=True)      # 1.0 or 1.1
    final_weight = Column(Float, nullable=True)     # computed weight
    
    bucket_ts = Column(DateTime, nullable=True, index=True)
    created_at = Column(DateTime, default=func.now())
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "token": self.token,
            "url": self.url,
            "site_name": self.site_name,
            "title": self.title,
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "clean_content": self.clean_content,
            "word_count": self.word_count,
            "event_probs": self.event_probs,
            "sentiment_score": self.sentiment_score,
            "source_trust": self.source_trust,
            "recency_decay": self.recency_decay,
            "novelty_score": self.novelty_score,
            "proof_bonus": self.proof_bonus,
            "final_weight": self.final_weight,
            "bucket_ts": self.bucket_ts.isoformat() if self.bucket_ts else None,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }

class Bucket(Base):
    __tablename__ = "buckets"
    
    id = Column(Integer, primary_key=True, index=True)
    token = Column(String(20), index=True, nullable=False)
    bucket_ts = Column(DateTime, index=True, nullable=False)
    
    # Narrative metrics
    narrative_heat = Column(Float, nullable=True)      # NHS_t = Σ contrib_i
    positive_heat = Column(Float, nullable=True)       # contributions with sentiment > 0
    negative_heat = Column(Float, nullable=True)       # contributions with sentiment < 0
    consensus = Column(Float, nullable=True)           # fraction matching plurality event
    hype_velocity = Column(Float, nullable=True)       # (NHS_t - NHS_{t-1}) / max(|NHS_{t-1}|, 1)
    risk_polarity = Column(Float, nullable=True)       # negative if hack/regulatory dominates
    
    # Event distribution
    event_distribution = Column(JSON, nullable=True)  # {"listing": 0.6, "partnership": 0.4, ...}
    top_event = Column(String(50), nullable=True)
    
    # Optional on-chain features
    liquidity_usd = Column(Float, nullable=True)
    trades_count_change = Column(Integer, nullable=True)
    spread_estimate = Column(Float, nullable=True)
    
    # Additional metadata
    article_count = Column(Integer, nullable=True)
    avg_source_trust = Column(Float, nullable=True)
    avg_novelty = Column(Float, nullable=True)
    
    created_at = Column(DateTime, default=func.now())
    
    __table_args__ = (
        UniqueConstraint('token', 'bucket_ts', name='_token_bucket_uc'),
    )
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "token": self.token,
            "bucket_ts": self.bucket_ts.isoformat() if self.bucket_ts else None,
            "narrative_heat": self.narrative_heat,
            "positive_heat": self.positive_heat,
            "negative_heat": self.negative_heat,
            "consensus": self.consensus,
            "hype_velocity": self.hype_velocity,
            "risk_polarity": self.risk_polarity,
            "event_distribution": self.event_distribution,
            "top_event": self.top_event,
            "liquidity_usd": self.liquidity_usd,
            "trades_count_change": self.trades_count_change,
            "spread_estimate": self.spread_estimate,
            "article_count": self.article_count,
            "avg_source_trust": self.avg_source_trust,
            "avg_novelty": self.avg_novelty,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }

class Label(Base):
    __tablename__ = "labels"
    
    id = Column(Integer, primary_key=True, index=True)
    token = Column(String(20), index=True, nullable=False)
    bucket_ts = Column(DateTime, index=True, nullable=False)
    forward_return_60m = Column(Float, nullable=True)  # actual price change
    label_binary = Column(Integer, nullable=True)      # 1 if return > threshold, 0 else
    created_at = Column(DateTime, default=func.now())
    
    __table_args__ = (
        UniqueConstraint('token', 'bucket_ts', name='_token_bucket_label_uc'),
    )
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "token": self.token,
            "bucket_ts": self.bucket_ts.isoformat() if self.bucket_ts else None,
            "forward_return_60m": self.forward_return_60m,
            "label_binary": self.label_binary,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }

class MLModel(Base):
    __tablename__ = "models"
    
    id = Column(Integer, primary_key=True, index=True)
    version = Column(String(20), unique=True, nullable=False)
    model_type = Column(String(50), nullable=False)   # "logistic", "lightgbm"
    parameters = Column(JSON, nullable=True)
    feature_names = Column(JSON, nullable=True)
    performance_metrics = Column(JSON, nullable=True)
    is_active = Column(Boolean, default=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "version": self.version,
            "model_type": self.model_type,
            "parameters": self.parameters,
            "feature_names": self.feature_names,
            "performance_metrics": self.performance_metrics,
            "is_active": self.is_active,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }

class TrackedToken(Base):
    __tablename__ = "tracked_tokens"
    
    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String(20), unique=True, nullable=False, index=True)
    name = Column(String(100), nullable=True)
    chain_id = Column(Integer, nullable=True)  # Ethereum=1, BSC=56, etc.
    contract_address = Column(String(42), nullable=True)  # Token contract address
    gecko_id = Column(String(100), nullable=True)  # GeckoTerminal ID for price data
    is_active = Column(Boolean, default=True, index=True)
    auto_analysis = Column(Boolean, default=False)  # Enable automatic periodic analysis
    analysis_interval_hours = Column(Integer, default=6)  # How often to analyze
    last_analysis_at = Column(DateTime, nullable=True)
    added_by = Column(String(42), nullable=True)  # Admin wallet address who added it
    token_metadata = Column(JSON, nullable=True)  # Additional token information
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "symbol": self.symbol,
            "name": self.name,
            "chain_id": self.chain_id,
            "contract_address": self.contract_address,
            "gecko_id": self.gecko_id,
            "is_active": self.is_active,
            "auto_analysis": self.auto_analysis,
            "analysis_interval_hours": self.analysis_interval_hours,
            "last_analysis_at": self.last_analysis_at.isoformat() if self.last_analysis_at else None,
            "added_by": self.added_by,
            "metadata": self.token_metadata,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }

class UserWallet(Base):
    """
    User wallet information and AgentChain.Trade managed deposit addresses
    """
    __tablename__ = "user_wallets"
    
    id = Column(Integer, primary_key=True, index=True)
    user_wallet_address = Column(String(42), unique=True, nullable=False, index=True)  # User's connected wallet
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    is_active = Column(Boolean, default=True)
    
    # Relationship to deposits
    deposits = relationship("UserDeposit", back_populates="user_wallet")
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "user_wallet_address": self.user_wallet_address,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }

class ManagedWallet(Base):
    """
    AgentChain.Trade managed wallets (0xgasless wallets) for each chain
    """
    __tablename__ = "managed_wallets"
    
    id = Column(Integer, primary_key=True, index=True)
    wallet_address = Column(String(42), nullable=False, index=True)  # AgentChain managed address
    chain_id = Column(Integer, nullable=False, index=True)
    wallet_type = Column(String(20), default="deposit")  # deposit, trading, treasury
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    
    # Unique constraint per chain
    __table_args__ = (UniqueConstraint('wallet_address', 'chain_id', name='unique_wallet_per_chain'),)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "wallet_address": self.wallet_address,
            "chain_id": self.chain_id,
            "wallet_type": self.wallet_type,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }

class UserDeposit(Base):
    """
    User deposits into AgentChain.Trade managed wallets
    """
    __tablename__ = "user_deposits"
    
    id = Column(Integer, primary_key=True, index=True)
    user_wallet_id = Column(Integer, ForeignKey("user_wallets.id"), nullable=False, index=True)
    managed_wallet_id = Column(Integer, ForeignKey("managed_wallets.id"), nullable=False, index=True)
    
    # Transaction details
    chain_id = Column(Integer, nullable=False, index=True)
    token_address = Column(String(42), nullable=True)  # NULL for native tokens (ETH, BNB, etc.)
    token_symbol = Column(String(20), nullable=False, index=True)
    amount = Column(String(78), nullable=False)  # Store as string to avoid precision issues
    decimal_places = Column(Integer, default=18)
    
    # Blockchain tracking
    transaction_hash = Column(String(66), unique=True, nullable=False, index=True)
    block_number = Column(Integer, nullable=True)
    from_address = Column(String(42), nullable=False)  # User's wallet address
    to_address = Column(String(42), nullable=False)    # AgentChain managed address
    
    # Status tracking
    status = Column(String(20), default="pending")  # pending, confirmed, failed
    confirmations = Column(Integer, default=0)
    confirmed_at = Column(DateTime, nullable=True)
    
    # Metadata
    gas_used = Column(String(20), nullable=True)
    gas_price = Column(String(30), nullable=True)
    usd_value_at_deposit = Column(String(20), nullable=True)  # USD value when deposited
    deposit_metadata = Column(JSON, nullable=True)  # Additional deposit information
    
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    
    # Relationships
    user_wallet = relationship("UserWallet", back_populates="deposits")
    managed_wallet = relationship("ManagedWallet")
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "user_wallet_id": self.user_wallet_id,
            "managed_wallet_id": self.managed_wallet_id,
            "chain_id": self.chain_id,
            "token_address": self.token_address,
            "token_symbol": self.token_symbol,
            "amount": self.amount,
            "decimal_places": self.decimal_places,
            "transaction_hash": self.transaction_hash,
            "block_number": self.block_number,
            "from_address": self.from_address,
            "to_address": self.to_address,
            "status": self.status,
            "confirmations": self.confirmations,
            "confirmed_at": self.confirmed_at.isoformat() if self.confirmed_at else None,
            "gas_used": self.gas_used,
            "gas_price": self.gas_price,
            "usd_value_at_deposit": self.usd_value_at_deposit,
            "metadata": self.deposit_metadata,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }

class UserBalance(Base):
    """
    Aggregated user balance across all chains and tokens
    """
    __tablename__ = "user_balances"
    
    id = Column(Integer, primary_key=True, index=True)
    user_wallet_id = Column(Integer, ForeignKey("user_wallets.id"), nullable=False, index=True)
    chain_id = Column(Integer, nullable=False, index=True)
    token_address = Column(String(42), nullable=True)  # NULL for native tokens
    token_symbol = Column(String(20), nullable=False, index=True)
    
    # Balance tracking
    total_deposited = Column(String(78), default="0")  # Total amount deposited
    total_withdrawn = Column(String(78), default="0")  # Total amount withdrawn
    available_balance = Column(String(78), default="0")  # Available for trading
    locked_balance = Column(String(78), default="0")    # Locked in trades/orders
    
    # Metadata
    decimal_places = Column(Integer, default=18)
    last_updated = Column(DateTime, default=func.now())
    created_at = Column(DateTime, default=func.now())
    
    # Unique constraint per user per token per chain
    __table_args__ = (
        UniqueConstraint('user_wallet_id', 'chain_id', 'token_symbol', name='unique_user_token_balance'),
    )
    
    # Relationships
    user_wallet = relationship("UserWallet")
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "user_wallet_id": self.user_wallet_id,
            "chain_id": self.chain_id,
            "token_address": self.token_address,
            "token_symbol": self.token_symbol,
            "total_deposited": self.total_deposited,
            "total_withdrawn": self.total_withdrawn,
            "available_balance": self.available_balance,
            "locked_balance": self.locked_balance,
            "decimal_places": self.decimal_places,
            "last_updated": self.last_updated.isoformat() if self.last_updated else None,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }

class WaitlistUser(Base):
    """
    Waitlist registration for AgentChain.Trade community and token airdrops
    """
    __tablename__ = "waitlist_users"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    wallet_address = Column(String(42), nullable=True, index=True)
    twitter_handle = Column(String(50), nullable=True)
    discord_handle = Column(String(50), nullable=True)
    registration_date = Column(DateTime, default=func.now(), nullable=False)
    email_verified = Column(Boolean, default=False)
    airdrop_eligible = Column(Boolean, default=True)
    airdrop_amount = Column(DECIMAL(precision=18, scale=8), nullable=True)
    early_access_granted = Column(Boolean, default=False)
    referral_code = Column(String(20), nullable=True, unique=True, index=True)
    referred_by = Column(Integer, ForeignKey("waitlist_users.id"), nullable=True)
    notification_preferences = Column(JSON, default=lambda: {"email": True, "airdrop": True, "updates": True})
    user_metadata = Column(JSON, default=dict)  # Renamed from 'metadata' to avoid SQLAlchemy conflict
    ip_address = Column(String(45), nullable=True)  # For analytics and fraud prevention
    user_agent = Column(Text, nullable=True)
    
    # Relationships
    referrals = relationship("WaitlistUser", backref=backref("referrer", remote_side=[id]))
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "email": self.email,
            "wallet_address": self.wallet_address,
            "twitter_handle": self.twitter_handle,
            "discord_handle": self.discord_handle,
            "registration_date": self.registration_date.isoformat() if self.registration_date else None,
            "email_verified": self.email_verified,
            "airdrop_eligible": self.airdrop_eligible,
            "airdrop_amount": str(self.airdrop_amount) if self.airdrop_amount else None,
            "early_access_granted": self.early_access_granted,
            "referral_code": self.referral_code,
            "referred_by": self.referred_by,
            "notification_preferences": self.notification_preferences,
            "user_metadata": self.user_metadata
        }
    
    def __repr__(self):
        return f"<WaitlistUser(email='{self.email}', registered='{self.registration_date}')>"