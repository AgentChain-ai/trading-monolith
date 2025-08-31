"""
Automated trading scheduler for portfolio rebalancing
Implements Phase 3.1 automated trading system
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import text

from ..database import get_db
from .portfolio_service import PortfolioService
from ..utils.monitoring import MetricsCollector

logger = logging.getLogger(__name__)

class TradingScheduler:
    """Automated trading scheduler for portfolio rebalancing"""
    
    def __init__(self):
        self.portfolio_service = PortfolioService()
        self.metrics = MetricsCollector()
        self.is_running = False
        self.rebalance_interval = 300  # 5 minutes in seconds
        self.last_rebalance_check = None
        
    async def start_scheduler(self):
        """Start the automated trading scheduler"""
        logger.info("Starting automated trading scheduler...")
        self.is_running = True
        
        while self.is_running:
            try:
                await self._run_rebalancing_cycle()
                await asyncio.sleep(self.rebalance_interval)
                
            except Exception as e:
                logger.error(f"Error in trading scheduler: {e}")
                await asyncio.sleep(60)  # Wait 1 minute before retrying
                
    async def stop_scheduler(self):
        """Stop the automated trading scheduler"""
        logger.info("Stopping automated trading scheduler...")
        self.is_running = False
        
    async def _run_rebalancing_cycle(self):
        """Run a complete rebalancing cycle for all active portfolios"""
        cycle_start = datetime.utcnow()
        logger.info(f"Starting rebalancing cycle at {cycle_start}")
        
        db_session = next(get_db())
        try:
            # Get all users with auto-trading enabled
            active_users = await self._get_auto_trading_users(db_session)
            logger.info(f"Found {len(active_users)} users with auto-trading enabled")
            
            rebalance_results = []
            
            for user_address in active_users:
                try:
                    # Check if user needs rebalancing
                    needs_rebalance = await self._should_rebalance_user(user_address, db_session)
                    
                    if needs_rebalance:
                        logger.info(f"Rebalancing portfolio for user {user_address}")
                        result = await self._execute_user_rebalance(user_address, db_session)
                        rebalance_results.append(result)
                        
                        # Small delay between user rebalances
                        await asyncio.sleep(1)
                        
                except Exception as e:
                    logger.error(f"Failed to rebalance user {user_address}: {e}")
                    rebalance_results.append({
                        "user_address": user_address,
                        "status": "failed",
                        "error": str(e)
                    })
            
            # Update metrics
            await self._update_rebalancing_metrics(rebalance_results)
            
            cycle_duration = (datetime.utcnow() - cycle_start).total_seconds()
            logger.info(f"Rebalancing cycle completed in {cycle_duration:.2f}s. "
                       f"Processed {len(active_users)} users, {len(rebalance_results)} rebalanced")
            
        except Exception as e:
            logger.error(f"Error in rebalancing cycle: {e}")
            
        finally:
            db_session.close()
            self.last_rebalance_check = datetime.utcnow()
    
    async def _get_auto_trading_users(self, db: Session) -> List[str]:
        """Get list of users with auto-trading enabled"""
        try:
            # Query users with auto-trading enabled and deposits
            query = text("""
                SELECT DISTINCT ub.user_address 
                FROM user_balances ub
                WHERE ub.balance_usd > 10  -- Minimum $10 portfolio
                AND ub.user_address IN (
                    SELECT user_address FROM user_deposits WHERE amount_usd > 0
                )
                -- For now, assume all users want auto-trading
                -- In production, add user_preferences table
            """)
            
            result = db.execute(query)
            users = [row[0] for row in result.fetchall()]
            return users
            
        except Exception as e:
            logger.error(f"Failed to get auto-trading users: {e}")
            return []
    
    async def _should_rebalance_user(self, user_address: str, db: Session) -> bool:
        """Check if a user's portfolio needs rebalancing"""
        try:
            # Get current portfolio
            portfolio = await self.portfolio_service.get_portfolio(user_address, db)
            if not portfolio:
                return False
            
            # Check minimum portfolio value
            total_value = portfolio.get("total_value_usd", 0)
            if total_value < 10:  # Skip small portfolios
                return False
            
            # Check last rebalance time
            last_rebalance = portfolio.get("last_rebalance")
            if last_rebalance:
                # Parse last rebalance time
                if isinstance(last_rebalance, str):
                    last_rebalance = datetime.fromisoformat(last_rebalance.replace('Z', '+00:00'))
                
                # Don't rebalance if done recently (< 4 hours)
                if datetime.utcnow() - last_rebalance.replace(tzinfo=None) < timedelta(hours=4):
                    return False
            
            # Check if significant rebalancing is needed
            current_allocations = {}
            for position in portfolio.get("positions", []):
                token = position["token"]
                allocation = position["allocation_percent"]
                current_allocations[token] = allocation
            
            # Get target allocations based on predictions
            target_allocations = await self.portfolio_service.calculate_target_allocation(user_address, db)
            
            # Check if allocations differ significantly (>5% for any token)
            max_deviation = 0
            for token, target_alloc in target_allocations.items():
                current_alloc = current_allocations.get(token, 0)
                deviation = abs(target_alloc - current_alloc)
                max_deviation = max(max_deviation, deviation)
            
            return max_deviation > 5.0  # Rebalance if >5% deviation
            
        except Exception as e:
            logger.error(f"Failed to check rebalancing need for {user_address}: {e}")
            return False
    
    async def _execute_user_rebalance(self, user_address: str, db: Session) -> Dict[str, Any]:
        """Execute portfolio rebalancing for a user"""
        try:
            # Generate rebalancing trades
            trades = await self.portfolio_service.generate_rebalancing_trades(user_address, db)
            
            if not trades:
                return {
                    "user_address": user_address,
                    "status": "no_trades_needed",
                    "trades_count": 0,
                    "value_moved": 0
                }
            
            # Execute trades (simulate for now)
            executed_trades = []
            total_value_moved = 0
            
            for trade in trades:
                # In production, integrate with 0xgasless microservice
                # For now, simulate successful execution
                executed_trade = {
                    "token": trade["token"],
                    "action": trade["action"],
                    "amount": trade["amount"],
                    "usd_value": trade["expected_usd"],
                    "status": "simulated_success",
                    "timestamp": datetime.utcnow().isoformat(),
                    "tx_hash": f"0x{trade['token'][:8]}...auto"
                }
                executed_trades.append(executed_trade)
                total_value_moved += trade["expected_usd"]
            
            # Record rebalance in database
            await self.portfolio_service.record_rebalance(user_address, executed_trades, db)
            
            logger.info(f"Successfully rebalanced {user_address}: "
                       f"{len(executed_trades)} trades, ${total_value_moved:.2f} moved")
            
            return {
                "user_address": user_address,
                "status": "success",
                "trades_count": len(executed_trades),
                "value_moved": total_value_moved,
                "trades": executed_trades
            }
            
        except Exception as e:
            logger.error(f"Failed to execute rebalance for {user_address}: {e}")
            return {
                "user_address": user_address,
                "status": "failed",
                "error": str(e),
                "trades_count": 0,
                "value_moved": 0
            }
    
    async def _update_rebalancing_metrics(self, results: List[Dict[str, Any]]):
        """Update system metrics after rebalancing cycle"""
        try:
            successful_rebalances = len([r for r in results if r["status"] == "success"])
            failed_rebalances = len([r for r in results if r["status"] == "failed"])
            total_value_moved = sum(r.get("value_moved", 0) for r in results)
            total_trades = sum(r.get("trades_count", 0) for r in results)
            
            # Update metrics
            self.metrics.increment_counter("portfolio_rebalances_total", successful_rebalances)
            self.metrics.increment_counter("portfolio_rebalance_failures", failed_rebalances)
            self.metrics.set_gauge("portfolio_total_value_moved", total_value_moved)
            self.metrics.set_gauge("portfolio_total_trades", total_trades)
            
            logger.info(f"Updated rebalancing metrics: "
                       f"{successful_rebalances} successful, {failed_rebalances} failed, "
                       f"${total_value_moved:.2f} moved, {total_trades} trades")
            
        except Exception as e:
            logger.error(f"Failed to update rebalancing metrics: {e}")
    
    async def get_scheduler_status(self) -> Dict[str, Any]:
        """Get current scheduler status"""
        return {
            "is_running": self.is_running,
            "rebalance_interval_seconds": self.rebalance_interval,
            "last_rebalance_check": self.last_rebalance_check.isoformat() if self.last_rebalance_check else None,
            "next_check_in_seconds": self.rebalance_interval - (
                (datetime.utcnow() - self.last_rebalance_check).total_seconds()
                if self.last_rebalance_check else 0
            ) if self.last_rebalance_check else 0
        }

# Global scheduler instance
trading_scheduler = TradingScheduler()

async def start_trading_scheduler():
    """Start the global trading scheduler"""
    await trading_scheduler.start_scheduler()

async def stop_trading_scheduler():
    """Stop the global trading scheduler"""
    await trading_scheduler.stop_scheduler()

def get_trading_scheduler() -> TradingScheduler:
    """Get the global trading scheduler instance"""
    return trading_scheduler
