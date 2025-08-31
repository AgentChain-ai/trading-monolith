"""
Portfolio Management Service
Handles portfolio tracking, analysis, and rebalancing for AgentChain.Trade
"""

import logging
import asyncio
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from decimal import Decimal
from sqlalchemy.orm import Session
from sqlalchemy import desc, and_, func

from ..database import SessionLocal
from ..models import UserBalance, ManagedWallet, Bucket, Article, UserDeposit
from ..services.ml_engine import MLEngine
from ..services.gecko_client import GeckoTerminalClient

logger = logging.getLogger(__name__)

class PortfolioService:
    """Service for managing user portfolios and trading decisions"""
    
    def __init__(self):
        self.ml_engine = MLEngine()
        self.gecko_client = GeckoTerminalClient()
        self.rebalance_interval = 300  # 5 minutes in seconds
        self.min_prediction_confidence = 0.6  # Minimum confidence for trades
        self.max_single_token_weight = 0.3  # Maximum 30% allocation to single token
        self.min_trade_value_usd = 10.0  # Minimum trade value in USD
    
    async def get_user_portfolio(self, user_wallet_address: str, chain_id: int) -> Dict:
        """Get current portfolio for a user on a specific chain"""
        db = SessionLocal()
        try:
            # Get user balances
            balances = db.query(UserBalance).filter(
                and_(
                    UserBalance.user_wallet_address == user_wallet_address,
                    UserBalance.chain_id == chain_id,
                    UserBalance.balance > 0
                )
            ).all()
            
            portfolio = {
                'user_wallet_address': user_wallet_address,
                'chain_id': chain_id,
                'balances': {},
                'total_value_usd': Decimal('0.0'),
                'last_updated': datetime.utcnow().isoformat()
            }
            
            for balance in balances:
                # Get current price from GeckoTerminal
                price_data = await self._get_token_price(balance.token_symbol)
                current_price = Decimal(str(price_data.get('price', 0.0)))
                
                token_value = balance.balance * current_price
                portfolio['balances'][balance.token_symbol] = {
                    'balance': float(balance.balance),
                    'price_usd': float(current_price),
                    'value_usd': float(token_value),
                    'percentage': 0.0  # Will be calculated after total
                }
                portfolio['total_value_usd'] += token_value
            
            # Calculate percentages
            if portfolio['total_value_usd'] > 0:
                for token_data in portfolio['balances'].values():
                    token_data['percentage'] = (token_data['value_usd'] / float(portfolio['total_value_usd'])) * 100
            
            return portfolio
            
        except Exception as e:
            logger.error(f"Error getting portfolio for {user_wallet_address}: {e}")
            return {}
        finally:
            db.close()
    
    async def get_prediction_scores(self, top_n: int = 10) -> List[Dict]:
        """Get prediction scores for top N tokens"""
        db = SessionLocal()
        try:
            # Get tokens with recent data (last 24 hours)
            since = datetime.utcnow() - timedelta(hours=24)
            
            # Get latest buckets for each token
            latest_buckets = db.query(
                Bucket.token,
                func.max(Bucket.bucket_ts).label('latest_ts')
            ).filter(
                Bucket.bucket_ts >= since
            ).group_by(Bucket.token).subquery()
            
            # Get the actual latest bucket data
            buckets = db.query(Bucket).join(
                latest_buckets,
                and_(
                    Bucket.token == latest_buckets.c.token,
                    Bucket.bucket_ts == latest_buckets.c.latest_ts
                )
            ).all()
            
            predictions = []
            
            for bucket in buckets:
                try:
                    # Get ML prediction for this token
                    bucket_data = bucket.to_dict()
                    prediction_result = await self.ml_engine.predict(bucket_data)
                    
                    if prediction_result and prediction_result.get('confidence', 0) >= self.min_prediction_confidence:
                        predictions.append({
                            'token': bucket.token,
                            'prediction_score': prediction_result.get('probability_up', 0.5),
                            'confidence': prediction_result.get('confidence', 0.0),
                            'bucket_ts': bucket.bucket_ts.isoformat(),
                            'article_count': bucket.article_count or 0,
                            'sentiment_score': bucket.sentiment_score or 0.0
                        })
                        
                except Exception as e:
                    logger.warning(f"Error getting prediction for {bucket.token}: {e}")
                    continue
            
            # Sort by prediction score (descending) and return top N
            predictions.sort(key=lambda x: x['prediction_score'], reverse=True)
            return predictions[:top_n]
            
        except Exception as e:
            logger.error(f"Error getting prediction scores: {e}")
            return []
        finally:
            db.close()
    
    async def calculate_target_allocation(self, predictions: List[Dict], total_portfolio_value: Decimal) -> Dict[str, Decimal]:
        """Calculate target allocation based on prediction scores"""
        if not predictions or total_portfolio_value <= 0:
            return {}
        
        # Calculate total prediction score
        total_score = sum(pred['prediction_score'] for pred in predictions)
        
        if total_score <= 0:
            return {}
        
        target_allocation = {}
        
        for prediction in predictions:
            # Calculate weight based on prediction score
            raw_weight = prediction['prediction_score'] / total_score
            
            # Apply maximum single token weight limit
            weight = min(raw_weight, self.max_single_token_weight)
            
            # Calculate target amount
            target_amount = total_portfolio_value * Decimal(str(weight))
            
            # Only include if above minimum trade value
            if target_amount >= Decimal(str(self.min_trade_value_usd)):
                target_allocation[prediction['token']] = target_amount
        
        return target_allocation
    
    async def generate_rebalancing_trades(self, user_address: str, db: Session) -> List[Dict]:
        """Generate list of trades needed to rebalance portfolio"""
        try:
            # Get user's chain - use first chain with deposits
            user_deposits = db.query(UserDeposit.chain_id).filter(
                UserDeposit.user_wallet_address == user_address
            ).distinct().first()
            
            if not user_deposits:
                return []
            
            chain_id = user_deposits[0]
            
            # Get current portfolio
            portfolio = await self.get_user_portfolio(user_address, chain_id)
            
            if not portfolio or portfolio['total_value_usd'] <= 0:
                logger.info(f"No portfolio found for {user_address} on chain {chain_id}")
                return []
            
            # Get prediction scores
            predictions = await self.get_prediction_scores()
            
            if not predictions:
                logger.info("No predictions available for rebalancing")
                return []
            
            # Calculate target allocation
            target_allocation = await self.calculate_target_allocation(
                predictions, 
                portfolio['total_value_usd']
            )
            
            if not target_allocation:
                logger.info("No target allocation calculated")
                return []
            
            # Generate trades
            trades = []
            current_balances = portfolio['balances']
            
            # Calculate trades needed
            for token, target_value in target_allocation.items():
                current_value = Decimal(str(current_balances.get(token, {}).get('value_usd', 0.0)))
                value_diff = target_value - current_value
                
                # Only trade if difference is significant
                if abs(value_diff) >= Decimal(str(self.min_trade_value_usd)):
                    trade_action = 'BUY' if value_diff > 0 else 'SELL'
                    
                    trades.append({
                        'token': token,
                        'action': trade_action,
                        'current_value_usd': float(current_value),
                        'target_value_usd': float(target_value),
                        'trade_value_usd': float(abs(value_diff)),
                        'prediction_score': next(p['prediction_score'] for p in predictions if p['token'] == token),
                        'confidence': next(p['confidence'] for p in predictions if p['token'] == token),
                        'priority': float(abs(value_diff))  # Used for ordering trades
                    })
            
            # Handle tokens not in target allocation (sell all)
            for token in current_balances:
                if token not in target_allocation:
                    current_value = Decimal(str(current_balances[token]['value_usd']))
                    if current_value >= Decimal(str(self.min_trade_value_usd)):
                        trades.append({
                            'token': token,
                            'action': 'SELL',
                            'current_value_usd': float(current_value),
                            'target_value_usd': 0.0,
                            'trade_value_usd': float(current_value),
                            'prediction_score': 0.0,
                            'confidence': 0.0,
                            'priority': float(current_value)
                        })
            
            # Sort trades by priority (highest value first)
            trades.sort(key=lambda x: x['priority'], reverse=True)
            
            logger.info(f"Generated {len(trades)} rebalancing trades for {user_address}")
            return trades
            
        except Exception as e:
            logger.error(f"Error generating rebalancing trades: {e}")
            return []
    
    async def _get_token_price(self, token_symbol: str) -> Dict:
        """Get current token price from GeckoTerminal"""
        try:
            # Try to get price data (implement based on your GeckoTerminal integration)
            # For now, return mock data
            return {
                'price': 1.0,  # USD price
                'price_change_24h': 0.0
            }
        except Exception as e:
            logger.warning(f"Error getting price for {token_symbol}: {e}")
            return {'price': 1.0, 'price_change_24h': 0.0}
    
    async def get_portfolio_performance(self, user_wallet_address: str, chain_id: int, days: int = 7) -> Dict:
        """Get portfolio performance metrics"""
        db = SessionLocal()
        try:
            # Get historical deposits for baseline
            since = datetime.utcnow() - timedelta(days=days)
            
            deposits = db.query(UserDeposit).filter(
                and_(
                    UserDeposit.user_wallet_address == user_wallet_address,
                    UserDeposit.chain_id == chain_id,
                    UserDeposit.created_at >= since,
                    UserDeposit.status == 'confirmed'
                )
            ).all()
            
            # Calculate total deposits
            total_deposited = sum(float(deposit.amount) for deposit in deposits)
            
            # Get current portfolio value
            portfolio = await self.get_user_portfolio(user_wallet_address, chain_id)
            current_value = float(portfolio.get('total_value_usd', 0.0))
            
            # Calculate performance
            if total_deposited > 0:
                profit_loss = current_value - total_deposited
                profit_loss_percentage = (profit_loss / total_deposited) * 100
            else:
                profit_loss = 0.0
                profit_loss_percentage = 0.0
            
            return {
                'total_deposited_usd': total_deposited,
                'current_value_usd': current_value,
                'profit_loss_usd': profit_loss,
                'profit_loss_percentage': profit_loss_percentage,
                'period_days': days,
                'last_updated': datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error calculating portfolio performance: {e}")
            return {}
        finally:
            db.close()
    
    # Additional methods needed by API endpoints
    
    async def get_portfolio(self, user_address: str, db: Session) -> Optional[Dict]:
        """Get portfolio overview for API endpoint"""
        try:
            # Get all chains the user has deposits on
            user_deposits = db.query(UserDeposit.chain_id).filter(
                UserDeposit.user_wallet_address == user_address
            ).distinct().all()
            
            if not user_deposits:
                return None
            
            # For simplicity, use first chain found
            # In production, aggregate across all chains
            chain_id = user_deposits[0][0]
            
            # Get portfolio for the chain
            portfolio = await self.get_user_portfolio(user_address, chain_id)
            
            # Convert to expected format
            positions = []
            for token, balance_info in portfolio['balances'].items():
                positions.append({
                    'token': token,
                    'balance': float(balance_info['balance']),
                    'value_usd': float(balance_info['value_usd']),
                    'allocation_percent': float(balance_info['allocation_percent']),
                    'price_change_24h': balance_info.get('price_change_24h', 0.0)
                })
            
            return {
                'user_address': user_address,
                'status': 'active' if positions else 'no_portfolio',
                'total_value_usd': float(portfolio['total_value_usd']),
                'positions': positions,
                'last_rebalance': None,  # TODO: Track rebalance history
                'performance': {
                    'total_return': 12.5,  # Mock data
                    'daily_return': 1.8,
                    'trades_count': 5
                }
            }
            
        except Exception as e:
            logger.error(f"Failed to get portfolio for {user_address}: {e}")
            return None
    
    async def record_rebalance(self, user_address: str, trades: List[Dict], db: Session) -> bool:
        """Record a rebalancing operation"""
        try:
            # In production, store rebalance history in database
            logger.info(f"Recording rebalance for {user_address}: {len(trades)} trades")
            return True
        except Exception as e:
            logger.error(f"Failed to record rebalance for {user_address}: {e}")
            return False
    
    async def get_token_prediction(self, token: str, db: Session) -> Optional[Dict]:
        """Get ML prediction for a specific token"""
        try:
            # Use existing ML engine
            features = await self._get_latest_features(token, db)
            if not features:
                return None
            
            prediction = await self.ml_engine.predict(features)
            
            return {
                'token': token,
                'prediction_score': prediction.get('confidence', 0.5),
                'direction': 'bullish' if prediction.get('confidence', 0.5) > 0.6 else 'bearish',
                'confidence': prediction.get('confidence', 0.5),
                'timestamp': datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Failed to get prediction for {token}: {e}")
            return None
    
    async def _get_latest_features(self, token: str, db: Session) -> Optional[Dict]:
        """Get latest features for a token"""
        try:
            # Get latest bucket for the token
            latest_bucket = db.query(Bucket).filter(
                Bucket.token == token
            ).order_by(desc(Bucket.bucket_ts)).first()
            
            if not latest_bucket:
                return None
            
            return {
                'sentiment_score': float(latest_bucket.sentiment_score or 0),
                'volume_score': float(latest_bucket.volume_score or 0),
                'momentum_score': float(latest_bucket.momentum_score or 0),
                'social_score': float(latest_bucket.social_score or 0)
            }
            
        except Exception as e:
            logger.error(f"Failed to get features for {token}: {e}")
            return None
    
    async def get_performance_metrics(self, user_address: str, days: int, db: Session) -> Dict:
        """Get portfolio performance metrics"""
        # Mock implementation for now
        return {
            'period_days': days,
            'total_return_pct': 15.3,
            'daily_returns': [],
            'max_drawdown': -3.2,
            'sharpe_ratio': 1.8,
            'win_rate': 0.75,
            'total_trades': 12
        }
    
    async def set_auto_trading(self, user_address: str, enabled: bool, db: Session) -> bool:
        """Enable/disable auto-trading for user"""
        try:
            # In production, store user preferences in database
            logger.info(f"Auto-trading {'enabled' if enabled else 'disabled'} for {user_address}")
            return True
        except Exception as e:
            logger.error(f"Failed to set auto-trading for {user_address}: {e}")
            return False
    
    async def get_trade_history(self, user_address: str, limit: int, db: Session) -> List[Dict]:
        """Get trade history for user"""
        # Mock implementation - in production, query trade history table
        return [
            {
                'token': 'ETH',
                'action': 'buy',
                'amount': 0.5,
                'usd_value': 1250.0,
                'status': 'executed',
                'timestamp': (datetime.utcnow() - timedelta(hours=2)).isoformat(),
                'tx_hash': '0xabc123...def456'
            },
            {
                'token': 'USDC',
                'action': 'sell',
                'amount': 500.0,
                'usd_value': 500.0,
                'status': 'executed',
                'timestamp': (datetime.utcnow() - timedelta(hours=6)).isoformat(),
                'tx_hash': '0xdef456...ghi789'
            }
        ]
    
    async def get_system_analytics(self, db: Session) -> Dict:
        """Get system-wide portfolio analytics"""
        try:
            # Count total users with portfolios
            total_users = db.query(UserDeposit.user_wallet_address).distinct().count()
            
            # Calculate total system value
            total_balances = db.query(
                func.sum(UserBalance.balance_usd)
            ).scalar() or 0
            
            return {
                'total_users': total_users,
                'total_portfolio_value_usd': float(total_balances),
                'active_trading_users': total_users,  # Mock for now
                'total_trades_today': 45,  # Mock
                'average_portfolio_size': float(total_balances / max(total_users, 1)),
                'top_performing_token': 'ETH',  # Mock
                'system_health': 'good'
            }
            
        except Exception as e:
            logger.error(f"Failed to get system analytics: {e}")
            return {
                'total_users': 0,
                'total_portfolio_value_usd': 0,
                'active_trading_users': 0,
                'total_trades_today': 0,
                'average_portfolio_size': 0,
                'top_performing_token': 'N/A',
                'system_health': 'error'
            }
