import httpx
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import and_

from ..models import UserWallet, ManagedWallet, UserDeposit, UserBalance

logger = logging.getLogger(__name__)

class DepositService:
    """Service for managing user deposits through 0xgasless managed wallets"""
    
    def __init__(self, microservice_url: str = "http://localhost:3003"):
        self.microservice_url = microservice_url
        self.timeout = httpx.Timeout(30.0)
    
    async def get_supported_chains(self) -> List[Dict[str, Any]]:
        """Get list of supported blockchain networks from microservice"""
        try:
            # Dynamically detect which chain the microservice is configured for
            # by checking what addresses it returns
            _ = await self._get_microservice_chain_info()
            
            # Return both chains for UI flexibility, but only the microservice chain will work
            return [
                {
                    "chainId": 43114,
                    "name": "Avalanche",
                    "nativeCurrency": "AVAX"
                },
                {
                    "chainId": 43113,
                    "name": "Avalanche Fuji Testnet",
                    "nativeCurrency": "AVAX"
                }
            ]
        except Exception as e:
            logger.error(f"Failed to get supported chains: {e}")
            raise
    
    async def _get_microservice_chain_info(self) -> Dict[str, Any]:
        """Get the actual chain info from the microservice"""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                # Get health endpoint or check what chain the microservice is on
                balance_response = await client.get(f"{self.microservice_url}/api/swap/balance")
                balance_response.raise_for_status()
                _ = balance_response.json()
                
                # The microservice is configured for a specific chain
                # For now, assume it's mainnet unless we can detect otherwise
                return {
                    "chainId": 43114,  # Default to mainnet based on .env
                    "chainName": "Avalanche"
                }
        except Exception as e:
            logger.error(f"Failed to get microservice chain info: {e}")
            return {"chainId": 43114, "chainName": "Avalanche"}
        except Exception as e:
            logger.error(f"Failed to get supported chains: {e}")
            raise
    
    async def get_managed_wallet_addresses(self) -> List[Dict[str, Any]]:
        """Get AgentChain managed wallet addresses for all supported chains"""
        try:
            # Get addresses from the working endpoints
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                # Get Smart Account address
                address_response = await client.get(f"{self.microservice_url}/api/swap/address")
                address_response.raise_for_status()
                address_data = address_response.json()
                
                # Get balance info (which includes EOA address)
                balance_response = await client.get(f"{self.microservice_url}/api/swap/balance")
                balance_response.raise_for_status()
                balance_data = balance_response.json()
                
                if not address_data.get("success") or not balance_data.get("success"):
                    raise Exception("Microservice returned error")
                
                # Extract Smart Account address from the result text
                smart_account = ""
                address_text = address_data["data"].get("result", "")
                # Look for addresses in bold markdown format or just hex addresses
                import re
                address_matches = re.findall(r'\*\*0x[a-fA-F0-9]{40}\*\*|0x[a-fA-F0-9]{40}', address_text)
                if address_matches:
                    # Remove markdown formatting if present
                    smart_account = address_matches[0].replace('**', '')
                
                # Extract EOA address from balance result text
                balance_text = balance_data["data"].get("result", "")
                eoa_address = ""
                # Look for "EOA:" followed by an address or addresses in bold
                eoa_matches = re.findall(r'EOA:\s*0x[a-fA-F0-9]{40}|\*\*0x[a-fA-F0-9]{40}\*\*', balance_text)
                if eoa_matches:
                    # Extract just the address part
                    eoa_match = eoa_matches[0]
                    if "EOA:" in eoa_match:
                        eoa_address = eoa_match.split("EOA:")[-1].strip()
                    else:
                        eoa_address = eoa_match.replace('**', '')
                
                logger.info(f"Extracted addresses - Smart Account: {smart_account}, EOA: {eoa_address}")
                
                # The microservice is currently configured for mainnet (43114)
                # Return addresses for both chains, but only mainnet will work
                return [
                    {
                        "chainId": 43114,
                        "chainName": "Avalanche",
                        "smartAccount": smart_account,
                        "eoaAddress": eoa_address,
                        "isActive": True
                    },
                    {
                        "chainId": 43113,
                        "chainName": "Avalanche Fuji Testnet",
                        "smartAccount": smart_account,  # Same addresses but different network
                        "eoaAddress": eoa_address,
                        "isActive": False  # Mark as inactive since microservice is on mainnet
                    }
                ]
                    
        except Exception as e:
            logger.error(f"Failed to get managed wallet addresses: {e}")
            raise
    
    async def get_managed_wallet_balances(self, chain_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """Get balances for managed wallets (all chains or specific chain)"""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                if chain_id:
                    url = f"{self.microservice_url}/api/balance/{chain_id}"
                else:
                    url = f"{self.microservice_url}/api/balance"
                
                response = await client.get(url)
                response.raise_for_status()
                data = response.json()
                
                if data.get("success"):
                    # Normalize single chain response to list format
                    balance_data = data.get("data", [])
                    if chain_id and isinstance(balance_data, dict):
                        balance_data = [balance_data]
                    return balance_data
                else:
                    raise Exception(f"Microservice error: {data}")
                    
        except Exception as e:
            logger.error(f"Failed to get managed wallet balances for chain {chain_id}: {e}")
            raise
    
    async def initialize_managed_wallets_async(self, db: Session) -> None:
        """Initialize managed wallet records in database for all supported chains (async version)"""
        try:
            # Get supported chains and addresses
            chains_data = await self.get_supported_chains()
            addresses_data = await self.get_managed_wallet_addresses()
            
            # Create a mapping of chain_id to addresses
            chain_addresses = {addr["chainId"]: addr for addr in addresses_data}
            
            for chain in chains_data:
                chain_id = chain["chainId"]
                
                # Check if managed wallet already exists
                existing_wallet = db.query(ManagedWallet).filter(
                    ManagedWallet.chain_id == chain_id
                ).first()
                
                if not existing_wallet and chain_id in chain_addresses:
                    addr_data = chain_addresses[chain_id]
                    
                    # Create new managed wallet record using Smart Account address
                    smart_account = addr_data.get("smartAccount", "")
                    if smart_account:
                        managed_wallet = ManagedWallet(
                            wallet_address=smart_account,
                            chain_id=chain_id,
                            wallet_type="deposit",
                            is_active=True,
                            created_at=datetime.utcnow()
                        )
                        
                        db.add(managed_wallet)
                        logger.info(f"Initialized managed wallet {smart_account} for {chain['name']} (chain {chain_id})")
            
            db.commit()
            logger.info("Managed wallet initialization complete")
            
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to initialize managed wallets: {e}")
            raise
    
    def initialize_managed_wallets(self, db: Session) -> None:
        """Initialize managed wallet records in database for all supported chains (sync wrapper)"""
        try:
            # Use a new event loop for this operation
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(self.initialize_managed_wallets_async(db))
            finally:
                loop.close()
                
        except Exception as e:
            logger.error(f"Failed to initialize managed wallets: {e}")
            raise
    
    def get_user_deposit_address(self, db: Session, user_wallet_address: str, chain_id: int) -> Optional[str]:
        """Get the deposit address for a user on a specific chain"""
        try:
            # Get or create user wallet record
            user_wallet = db.query(UserWallet).filter(
                UserWallet.user_wallet_address == user_wallet_address.lower()
            ).first()
            
            if not user_wallet:
                user_wallet = UserWallet(
                    user_wallet_address=user_wallet_address.lower(),
                    is_active=True,
                    created_at=datetime.utcnow()
                )
                db.add(user_wallet)
                db.commit()
            
            # Get managed wallet for the chain
            managed_wallet = db.query(ManagedWallet).filter(
                and_(
                    ManagedWallet.chain_id == chain_id,
                    ManagedWallet.is_active
                )
            ).first()
            
            if not managed_wallet:
                raise Exception(f"No managed wallet available for chain {chain_id}")
            
            # For now, all users deposit to the same managed wallet
            # In a production system, you might want user-specific deposit addresses
            return managed_wallet.wallet_address
            
        except Exception as e:
            logger.error(f"Failed to get deposit address for user {user_wallet_address} on chain {chain_id}: {e}")
            raise
    
    def record_deposit(self, db: Session, user_wallet_address: str, chain_id: int, 
                      token_symbol: str, amount: str, tx_hash: str) -> UserDeposit:
        """Record a user deposit transaction"""
        try:
            # Get user wallet
            user_wallet = db.query(UserWallet).filter(
                UserWallet.user_wallet_address == user_wallet_address.lower()
            ).first()
            
            if not user_wallet:
                raise Exception(f"User wallet {user_wallet_address} not found")
            
            # Get managed wallet
            managed_wallet = db.query(ManagedWallet).filter(
                and_(
                    ManagedWallet.chain_id == chain_id,
                    ManagedWallet.is_active
                )
            ).first()
            
            if not managed_wallet:
                raise Exception(f"No managed wallet available for chain {chain_id}")
            
            # Create deposit record
            deposit = UserDeposit(
                user_wallet_id=user_wallet.id,
                managed_wallet_id=managed_wallet.id,
                chain_id=chain_id,
                token_symbol=token_symbol.upper(),
                amount=amount,
                transaction_hash=tx_hash.lower(),
                from_address=user_wallet_address.lower(),
                to_address=managed_wallet.wallet_address.lower(),
                status="pending",
                created_at=datetime.utcnow()
            )
            
            db.add(deposit)
            db.commit()
            
            logger.info(f"Recorded deposit: {amount} {token_symbol} from {user_wallet_address} on chain {chain_id}")
            return deposit
            
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to record deposit: {e}")
            raise
    
    def update_deposit_status(self, db: Session, tx_hash: str, status: str, 
                             confirmed_at: Optional[datetime] = None) -> Optional[UserDeposit]:
        """Update the status of a deposit transaction"""
        try:
            deposit = db.query(UserDeposit).filter(
                UserDeposit.transaction_hash == tx_hash.lower()
            ).first()
            
            if not deposit:
                logger.warning(f"Deposit with tx_hash {tx_hash} not found")
                return None
            
            deposit.status = status
            if confirmed_at:
                deposit.confirmed_at = confirmed_at
            
            db.commit()
            
            # Update user balance if confirmed
            if status == "confirmed":
                self._update_user_balance(db, deposit)
            
            logger.info(f"Updated deposit {tx_hash} status to {status}")
            return deposit
            
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to update deposit status for {tx_hash}: {e}")
            raise
    
    def _update_user_balance(self, db: Session, deposit: UserDeposit) -> None:
        """Update user balance after confirmed deposit"""
        try:
            # Get or create user balance record
            user_balance = db.query(UserBalance).filter(
                and_(
                    UserBalance.user_wallet_id == deposit.user_wallet_id,
                    UserBalance.chain_id == deposit.chain_id,
                    UserBalance.token_symbol == deposit.token_symbol
                )
            ).first()
            
            if not user_balance:
                user_balance = UserBalance(
                    user_wallet_id=deposit.user_wallet_id,
                    chain_id=deposit.chain_id,
                    token_symbol=deposit.token_symbol,
                    balance="0",
                    updated_at=datetime.utcnow()
                )
                db.add(user_balance)
            
            # Add deposit amount to balance
            current_balance = float(user_balance.balance)
            deposit_amount = float(deposit.amount)
            new_balance = current_balance + deposit_amount
            
            user_balance.balance = str(new_balance)
            user_balance.updated_at = datetime.utcnow()
            
            db.commit()
            
            logger.info(f"Updated user balance: {deposit.token_symbol} balance now {new_balance}")
            
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to update user balance: {e}")
            raise
    
    def get_user_balances(self, db: Session, user_wallet_address: str) -> List[Dict[str, Any]]:
        """Get all balances for a user across all chains"""
        try:
            user_wallet = db.query(UserWallet).filter(
                UserWallet.user_wallet_address == user_wallet_address.lower()
            ).first()
            
            if not user_wallet:
                return []
            
            balances = db.query(UserBalance).filter(
                UserBalance.user_wallet_id == user_wallet.id
            ).all()
            
            result = []
            for balance in balances:
                managed_wallet = db.query(ManagedWallet).filter(
                    ManagedWallet.id == balance.managed_wallet_id
                ).first()
                
                result.append({
                    "chain_id": balance.chain_id,
                    "chain_name": managed_wallet.chain_name if managed_wallet else "Unknown",
                    "token_symbol": balance.token_symbol,
                    "balance": balance.balance,
                    "updated_at": balance.updated_at.isoformat()
                })
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to get user balances for {user_wallet_address}: {e}")
            raise
