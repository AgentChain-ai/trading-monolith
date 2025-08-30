import httpx
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from pydantic import BaseModel

from ..utils.resilience import (
    retry_with_fallback,
    RetryConfig,
    CircuitBreakerConfig,
    get_circuit_breaker,
    with_rate_limit,
    health_checker,
    fallback_cache
)

logger = logging.getLogger(__name__)

class OHLCVData(BaseModel):
    timestamp: int
    open: float
    high: float
    low: float
    close: float
    volume: float

class NetworkInfo(BaseModel):
    id: str
    name: str
    coingecko_asset_platform_id: str

class PoolInfo(BaseModel):
    id: str
    name: str
    address: str
    base_token_price_usd: Optional[float] = None
    quote_token_price_usd: Optional[float] = None
    volume_usd: Optional[float] = None
    liquidity_usd: Optional[float] = None

class GeckoTerminalClient:
    """Client for GeckoTerminal API with resilience features"""
    
    def __init__(self, base_url: str = "https://api.geckoterminal.com/api/v2"):
        self.base_url = base_url.rstrip('/')
        self.timeout = 30.0
        
        # Initialize circuit breaker
        self.circuit_breaker = get_circuit_breaker(
            "gecko_terminal",
            CircuitBreakerConfig(
                failure_threshold=5,
                timeout=60,  # 1 minute
                expected_exception=(httpx.HTTPError, httpx.ConnectError, httpx.TimeoutException)
            )
        )
        
        # Retry configuration for Gecko operations
        self.retry_config = RetryConfig(
            max_attempts=3,
            base_delay=0.5,
            max_delay=5.0,
            exponential_base=2.0,
            jitter=True
        )
        
        # Token mapping for common tokens to known pools
        self.token_pools = {
            "BTC": {
                "network": "eth",
                "pools": ["0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640"]  # WBTC/USDC
            },
            "ETH": {
                "network": "eth",
                "pools": ["0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640"]  # ETH/USDC
            },
            "USDC": {
                "network": "eth",
                "pools": ["0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640"]  # ETH/USDC
            },
            "SOL": {
                "network": "solana",
                "pools": ["FAqh648xeeaTqL7du49sztp9nfj5PjRQrfvaMccyd9cz"]  # SOL pool example
            }
        }
    
    def _get_fallback_price_data(self, token: str) -> Dict[str, Any]:
        """Get cached price data as fallback"""
        cache_key = f"price_data:{token.upper()}"
        cached_data = fallback_cache.get(cache_key)
        if cached_data:
            logger.info(f"Using cached price data for token: {token}")
            return cached_data
        return {}
    
    def _get_fallback_ohlcv_data(self, network: str, pool_address: str, timeframe: str) -> List[OHLCVData]:
        """Get cached OHLCV data as fallback"""
        cache_key = f"ohlcv:{network}:{pool_address}:{timeframe}"
        cached_data = fallback_cache.get(cache_key)
        if cached_data:
            logger.info(f"Using cached OHLCV data for {network}/{pool_address}")
            return [OHLCVData(**item) for item in cached_data]
        return []
        
    async def get_networks(self) -> List[NetworkInfo]:
        """Get list of available networks"""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(f"{self.base_url}/networks")
                response.raise_for_status()
                
                data = response.json()
                networks = []
                
                for item in data.get("data", []):
                    attrs = item.get("attributes", {})
                    networks.append(NetworkInfo(
                        id=item.get("id"),
                        name=attrs.get("name"),
                        coingecko_asset_platform_id=attrs.get("coingecko_asset_platform_id")
                    ))
                
                return networks
                
        except Exception as e:
            logger.error(f"Error getting networks: {e}")
            return []
    
    @retry_with_fallback(
        config=RetryConfig(max_attempts=3, base_delay=0.5, max_delay=3.0),
        circuit_breaker_name="gecko_terminal",
        expected_exceptions=(httpx.HTTPError, httpx.ConnectError, httpx.TimeoutException)
    )
    async def _get_ohlcv_with_retry(
        self,
        network: str,
        pool_address: str,
        timeframe: str = "day",
        limit: int = 100,
        before_timestamp: Optional[int] = None
    ) -> List[OHLCVData]:
        """Internal OHLCV method with retry logic"""
        url = f"{self.base_url}/networks/{network}/pools/{pool_address}/ohlcv/{timeframe}"
        
        params = {"limit": min(limit, 1000)}
        if before_timestamp:
            params["before_timestamp"] = before_timestamp
        
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            
            data = response.json()
            ohlcv_list = []
            
            for item in data.get("data", {}).get("attributes", {}).get("ohlcv_list", []):
                if len(item) >= 6:  # [timestamp, open, high, low, close, volume]
                    ohlcv_list.append(OHLCVData(
                        timestamp=int(item[0]),
                        open=float(item[1]),
                        high=float(item[2]),
                        low=float(item[3]),
                        close=float(item[4]),
                        volume=float(item[5]) if item[5] else 0.0
                    ))
            
            # Cache successful results
            cache_key = f"ohlcv:{network}:{pool_address}:{timeframe}"
            fallback_cache.set(cache_key, [
                {
                    "timestamp": item.timestamp,
                    "open": item.open,
                    "high": item.high,
                    "low": item.low,
                    "close": item.close,
                    "volume": item.volume
                } for item in ohlcv_list
            ], ttl=300)  # 5 minutes
            
            return ohlcv_list

    async def get_ohlcv_data(
        self,
        network: str,
        pool_address: str,
        timeframe: str = "day",
        limit: int = 100,
        before_timestamp: Optional[int] = None
    ) -> List[OHLCVData]:
        """
        Get OHLCV data for a specific pool with resilience features
        
        Args:
            network: Network ID (e.g., "eth", "bsc", "solana")
            pool_address: Pool contract address
            timeframe: "minute", "hour", "day"
            limit: Number of data points (max 1000)
            before_timestamp: Get data before this timestamp
            
        Returns:
            List of OHLCV data points
        """
        try:
            # Apply rate limiting
            return await with_rate_limit(
                "gecko",
                self._get_ohlcv_with_retry,
                network, pool_address, timeframe, limit, before_timestamp
            )
            
        except Exception as e:
            logger.error(f"OHLCV request failed for {network}/{pool_address}: {e}")
            
            # Try fallback from cache
            fallback_data = self._get_fallback_ohlcv_data(network, pool_address, timeframe)
            if fallback_data:
                return fallback_data
            
            # Return empty list if all else fails
            logger.warning(f"No fallback available for OHLCV: {network}/{pool_address}")
            return []
    
    async def get_token_pools(self, network: str, token_addresses: List[str]) -> List[PoolInfo]:
        """Get pool information for specific tokens"""
        try:
            url = f"{self.base_url}/networks/{network}/pools/multi/{','.join(token_addresses)}"
            
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url)
                response.raise_for_status()
                
                data = response.json()
                pools = []
                
                for item in data.get("data", []):
                    attrs = item.get("attributes", {})
                    pools.append(PoolInfo(
                        id=item.get("id"),
                        name=attrs.get("name", ""),
                        address=attrs.get("address", ""),
                        base_token_price_usd=attrs.get("base_token_price_usd"),
                        quote_token_price_usd=attrs.get("quote_token_price_usd"),
                        volume_usd=attrs.get("volume_usd", {}).get("h24"),
                        liquidity_usd=attrs.get("reserve_in_usd")
                    ))
                
                return pools
                
        except Exception as e:
            logger.error(f"Error getting token pools: {e}")
            return []
    
    async def get_token_price_data(self, token: str) -> Dict[str, Any]:
        """
        Get price and liquidity data for a token with auto-discovery support
        
        Args:
            token: Token symbol (ANY token symbol)
            
        Returns:
            Dictionary with price, volume, liquidity data
        """
        try:
            token_upper = token.upper()
            
            # Try auto-discovery if not in predefined mappings
            if token_upper not in self.token_pools:
                logger.info(f"Token {token_upper} not in predefined mappings, attempting auto-discovery")
                
                # Check fallback cache first
                fallback_data = self._get_fallback_price_data(token)
                if fallback_data:
                    return fallback_data
                
                # Try auto-discovery
                discovery_result = await self.discover_token_automatically(token)
                if discovery_result:
                    return discovery_result
                else:
                    logger.warning(f"Failed to auto-discover token: {token}")
                    return {}
            
            pool_config = self.token_pools[token_upper]
            network = pool_config["network"]
            pool_addresses = pool_config["pools"]
            
            # Get current price data from pools
            pools = await self.get_token_pools(network, pool_addresses)
            
            if not pools:
                # Try fallback if no pools found
                fallback_data = self._get_fallback_price_data(token)
                if fallback_data:
                    return fallback_data
                return {}
            
            # Use the first pool for now
            pool = pools[0]
            
            # Get recent OHLCV data (last 7 days) with resilience
            ohlcv_data = await self.get_ohlcv_data(network, pool.address, "day", 7)
            
            # Calculate price changes
            price_change_24h = 0.0
            price_change_7d = 0.0
            
            if len(ohlcv_data) >= 2:
                current_price = ohlcv_data[0].close
                yesterday_price = ohlcv_data[1].close
                price_change_24h = ((current_price - yesterday_price) / yesterday_price) * 100
                
                if len(ohlcv_data) >= 7:
                    week_ago_price = ohlcv_data[6].close
                    price_change_7d = ((current_price - week_ago_price) / week_ago_price) * 100
            
            result = {
                "token": token,
                "network": network,
                "pool_address": pool.address,
                "pool_name": pool.name,
                "price_usd": pool.base_token_price_usd or pool.quote_token_price_usd,
                "volume_24h_usd": pool.volume_usd,
                "liquidity_usd": pool.liquidity_usd,
                "price_change_24h": price_change_24h,
                "price_change_7d": price_change_7d,
                "ohlcv_data": [
                    {
                        "timestamp": item.timestamp,
                        "open": item.open,
                        "high": item.high,
                        "low": item.low,
                        "close": item.close,
                        "volume": item.volume
                    } for item in ohlcv_data[:7]  # Last 7 days
                ],
                "last_updated": datetime.utcnow().isoformat()
            }
            
            # Cache successful result
            cache_key = f"price_data:{token_upper}"
            fallback_cache.set(cache_key, result, ttl=300)  # 5 minutes
            
            return result
            
        except Exception as e:
            logger.error(f"Error getting token price data for {token}: {e}")
            
            # Try fallback from cache
            fallback_data = self._get_fallback_price_data(token)
            if fallback_data:
                return fallback_data
            
            # Return empty dict if all else fails
            logger.warning(f"No fallback available for token price data: {token}")
            return {}
    
    async def calculate_token_return(self, token: str, hours_back: int = 1) -> Optional[float]:
        """
        Calculate token return over specified time period
        
        Args:
            token: Token symbol
            hours_back: Hours to look back (1, 24, etc.)
            
        Returns:
            Return percentage or None if unavailable
        """
        try:
            price_data = await self.get_token_price_data(token)
            
            if not price_data or not price_data.get("ohlcv_data"):
                return None
            
            ohlcv = price_data["ohlcv_data"]
            
            if hours_back <= 24 and len(ohlcv) >= 2:
                # Use daily data for 24h return
                current_price = ohlcv[0]["close"]
                past_price = ohlcv[1]["close"]
                return ((current_price - past_price) / past_price) * 100
            
            return None
            
        except Exception as e:
            logger.error(f"Error calculating return for {token}: {e}")
            return None

    async def add_token_mapping(self, token: str, network: str, pools: List[str]):
        """Add new token pool mapping"""
        self.token_pools[token.upper()] = {
            "network": network,
            "pools": pools
        }
        logger.info(f"Added token mapping for {token}: {network} - {pools}")
    
    async def search_token_pools(self, token: str, networks: List[str] = None) -> List[Dict[str, Any]]:
        """
        Search for token pools across multiple networks
        
        Args:
            token: Token symbol or name to search for
            networks: List of network IDs to search in (default: popular networks)
            
        Returns:
            List of discovered pool information
        """
        if not networks:
            networks = ["eth", "bsc", "polygon", "arbitrum", "solana", "avalanche", "base"]
        
        all_pools = []
        token_lower = token.lower()
        
        for network in networks:
            try:
                # Search for pools containing the token
                pools = await self._search_network_pools(network, token_lower)
                for pool in pools:
                    pool["network"] = network
                all_pools.extend(pools)
                
            except Exception as e:
                logger.warning(f"Error searching {network} for token {token}: {e}")
                continue
        
        # Sort by liquidity (highest first) and return top results
        all_pools.sort(key=lambda x: x.get("liquidity_usd", 0) or 0, reverse=True)
        return all_pools[:10]  # Return top 10 pools
    
    async def _search_network_pools(self, network: str, token: str) -> List[Dict[str, Any]]:
        """Search for pools in a specific network"""
        try:
            # Try different endpoints to find token pools
            search_endpoints = [
                f"{self.base_url}/networks/{network}/trending_pools",
                f"{self.base_url}/networks/{network}/pools",
            ]
            
            for endpoint in search_endpoints:
                try:
                    async with httpx.AsyncClient(timeout=self.timeout) as client:
                        response = await client.get(endpoint, params={"page": 1})
                        if response.status_code == 200:
                            data = response.json()
                            pools = []
                            
                            for item in data.get("data", []):
                                attrs = item.get("attributes", {})
                                pool_name = (attrs.get("name", "").lower())
                                
                                # Check if token appears in pool name
                                if token in pool_name:
                                    pools.append({
                                        "id": item.get("id"),
                                        "name": attrs.get("name", ""),
                                        "address": attrs.get("address", ""),
                                        "base_token_price_usd": attrs.get("base_token_price_usd"),
                                        "quote_token_price_usd": attrs.get("quote_token_price_usd"),
                                        "volume_usd": attrs.get("volume_usd", {}).get("h24", 0),
                                        "liquidity_usd": attrs.get("reserve_in_usd", 0)
                                    })
                            
                            if pools:
                                return pools
                                
                except Exception as endpoint_error:
                    logger.debug(f"Search endpoint {endpoint} failed: {endpoint_error}")
                    continue
            
            return []
            
        except Exception as e:
            logger.error(f"Error searching network {network}: {e}")
            return []
    
    async def discover_token_automatically(self, token: str) -> Dict[str, Any]:
        """
        Automatically discover token information and add to mappings
        
        Args:
            token: Token symbol to discover
            
        Returns:
            Token information or empty dict if not found
        """
        try:
            token_upper = token.upper()
            logger.info(f"Auto-discovering token: {token_upper}")
            
            # Search for pools across networks
            discovered_pools = await self.search_token_pools(token)
            
            if not discovered_pools:
                logger.warning(f"No pools found for token: {token}")
                return {}
            
            # Select the best pool (highest liquidity)
            best_pool = discovered_pools[0]
            network = best_pool["network"]
            pool_address = best_pool["address"]
            
            # Add to token mappings
            if pool_address:
                self.token_pools[token_upper] = {
                    "network": network,
                    "pools": [pool_address]
                }
                
                logger.info(f"Auto-discovered {token_upper}: {network}/{pool_address} (liquidity: ${best_pool.get('liquidity_usd', 0):,.0f})")
                
                # Get comprehensive token data
                token_data = await self.get_token_price_data(token_upper)
                
                # Add discovery metadata
                token_data.update({
                    "auto_discovered": True,
                    "discovery_timestamp": datetime.utcnow().isoformat(),
                    "alternative_pools": discovered_pools[1:5],  # Store alternative pools
                    "total_pools_found": len(discovered_pools)
                })
                
                return token_data
            else:
                logger.warning(f"No valid pool address found for token: {token}")
                return {}
                
        except Exception as e:
            logger.error(f"Error auto-discovering token {token}: {e}")
            return {}
    
    async def validate_token(self, token: str) -> Dict[str, Any]:
        """
        Validate if a token exists and get basic information
        
        Args:
            token: Token symbol to validate
            
        Returns:
            Validation result with token info or error details
        """
        try:
            token_upper = token.upper()
            
            # Check if already mapped
            if token_upper in self.token_pools:
                return {
                    "valid": True,
                    "token": token_upper,
                    "source": "predefined_mapping",
                    "networks": [self.token_pools[token_upper]["network"]],
                    "pool_count": len(self.token_pools[token_upper]["pools"])
                }
            
            # Try to discover automatically
            discovery_result = await self.discover_token_automatically(token)
            
            if discovery_result:
                return {
                    "valid": True,
                    "token": token_upper,
                    "source": "auto_discovery",
                    "networks": [discovery_result.get("network")],
                    "pool_count": discovery_result.get("total_pools_found", 0),
                    "liquidity_usd": discovery_result.get("liquidity_usd"),
                    "price_usd": discovery_result.get("price_usd")
                }
            else:
                return {
                    "valid": False,
                    "token": token_upper,
                    "source": "not_found",
                    "error": "Token not found in any supported network",
                    "suggestion": "Check token symbol or try alternative networks"
                }
                
        except Exception as e:
            logger.error(f"Error validating token {token}: {e}")
            return {
                "valid": False,
                "token": token.upper(),
                "source": "error",
                "error": str(e)
            }
    
    async def get_supported_networks(self) -> List[Dict[str, Any]]:
        """Get list of supported networks with metadata"""
        try:
            networks_info = await self.get_networks()
            
            # Add popular network priorities
            popular_networks = {
                "eth": {"priority": 1, "name": "Ethereum", "popular": True},
                "bsc": {"priority": 2, "name": "Binance Smart Chain", "popular": True},
                "polygon": {"priority": 3, "name": "Polygon", "popular": True},
                "arbitrum": {"priority": 4, "name": "Arbitrum", "popular": True},
                "solana": {"priority": 5, "name": "Solana", "popular": True},
                "avalanche": {"priority": 6, "name": "Avalanche", "popular": True},
                "base": {"priority": 7, "name": "Base", "popular": True}
            }
            
            result = []
            for network in networks_info:
                network_id = network.id
                network_info = {
                    "id": network_id,
                    "name": network.name,
                    "coingecko_id": network.coingecko_asset_platform_id,
                    "popular": network_id in popular_networks,
                    "priority": popular_networks.get(network_id, {}).get("priority", 999)
                }
                result.append(network_info)
            
            # Sort by priority (popular networks first)
            result.sort(key=lambda x: x["priority"])
            return result
            
        except Exception as e:
            logger.error(f"Error getting supported networks: {e}")
            return []