"""
Resilience utilities for external API calls
Includes retry logic, circuit breakers, and fallback mechanisms
"""

import asyncio
import time
import logging
from typing import Any, Callable, Dict, List, Optional, Union, TypeVar
from functools import wraps
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timedelta
import httpx
import aiohttp

logger = logging.getLogger(__name__)

T = TypeVar('T')

class CircuitState(Enum):
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Circuit is open, failing fast
    HALF_OPEN = "half_open"  # Testing if service recovered

@dataclass
class RetryConfig:
    """Configuration for retry behavior"""
    max_attempts: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    exponential_base: float = 2.0
    jitter: bool = True
    backoff_strategy: str = "exponential"  # "exponential", "linear", "fixed"
    
@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker behavior"""
    failure_threshold: int = 5
    timeout: int = 60  # seconds
    expected_exception: Union[Exception, tuple] = (Exception,)
    recovery_timeout: int = 30

@dataclass
class CircuitBreakerState:
    """State tracking for circuit breaker"""
    state: CircuitState = CircuitState.CLOSED
    failure_count: int = 0
    last_failure_time: Optional[datetime] = None
    next_attempt_time: Optional[datetime] = None
    success_count: int = 0

class RateLimiter:
    """Token bucket rate limiter"""
    
    def __init__(self, rate: float, burst: int = 10):
        self.rate = rate  # tokens per second
        self.burst = burst  # maximum tokens
        self.tokens = burst
        self.last_refill = time.time()
        
    async def acquire(self, tokens: int = 1) -> bool:
        """Acquire tokens, returns True if successful"""
        now = time.time()
        # Add tokens based on time elapsed
        self.tokens = min(self.burst, self.tokens + (now - self.last_refill) * self.rate)
        self.last_refill = now
        
        if self.tokens >= tokens:
            self.tokens -= tokens
            return True
        return False
        
    async def wait_for_token(self, tokens: int = 1):
        """Wait until tokens are available"""
        while not await self.acquire(tokens):
            await asyncio.sleep(0.1)

class CircuitBreaker:
    """Circuit breaker implementation"""
    
    def __init__(self, config: CircuitBreakerConfig):
        self.config = config
        self.state = CircuitBreakerState()
        self._lock = asyncio.Lock()
        
    async def call(self, func: Callable[..., T], *args, **kwargs) -> T:
        """Execute function with circuit breaker protection"""
        async with self._lock:
            if self.state.state == CircuitState.OPEN:
                if datetime.now() < self.state.next_attempt_time:
                    raise Exception("Circuit breaker is OPEN")
                else:
                    self.state.state = CircuitState.HALF_OPEN
                    logger.info("Circuit breaker transitioning to HALF_OPEN")
        
        try:
            result = await func(*args, **kwargs) if asyncio.iscoroutinefunction(func) else func(*args, **kwargs)
            await self._on_success()
            return result
        except self.config.expected_exception as e:
            await self._on_failure()
            raise e
            
    async def _on_success(self):
        """Handle successful call"""
        async with self._lock:
            if self.state.state == CircuitState.HALF_OPEN:
                self.state.success_count += 1
                if self.state.success_count >= 3:  # Require 3 successes to close
                    self.state.state = CircuitState.CLOSED
                    self.state.failure_count = 0
                    self.state.success_count = 0
                    logger.info("Circuit breaker is now CLOSED")
            else:
                self.state.failure_count = 0
                
    async def _on_failure(self):
        """Handle failed call"""
        async with self._lock:
            self.state.failure_count += 1
            self.state.last_failure_time = datetime.now()
            
            if self.state.failure_count >= self.config.failure_threshold:
                self.state.state = CircuitState.OPEN
                self.state.next_attempt_time = datetime.now() + timedelta(seconds=self.config.timeout)
                logger.warning(f"Circuit breaker is now OPEN (failures: {self.state.failure_count})")

# Global circuit breakers for different services
_circuit_breakers: Dict[str, CircuitBreaker] = {}

def get_circuit_breaker(service_name: str, config: Optional[CircuitBreakerConfig] = None) -> CircuitBreaker:
    """Get or create circuit breaker for a service"""
    if service_name not in _circuit_breakers:
        config = config or CircuitBreakerConfig()
        _circuit_breakers[service_name] = CircuitBreaker(config)
    return _circuit_breakers[service_name]

def calculate_delay(attempt: int, config: RetryConfig) -> float:
    """Calculate retry delay based on strategy"""
    if config.backoff_strategy == "exponential":
        delay = min(config.base_delay * (config.exponential_base ** (attempt - 1)), config.max_delay)
    elif config.backoff_strategy == "linear":
        delay = min(config.base_delay * attempt, config.max_delay)
    else:  # fixed
        delay = config.base_delay
    
    # Add jitter to prevent thundering herd
    if config.jitter:
        import random
        delay *= (0.5 + random.random() * 0.5)
    
    return delay

def retry_with_fallback(
    config: Optional[RetryConfig] = None,
    circuit_breaker_name: Optional[str] = None,
    fallback_func: Optional[Callable] = None,
    expected_exceptions: tuple = (Exception,)
):
    """Decorator for retry logic with optional circuit breaker and fallback"""
    
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        
        @wraps(func)
        async def async_wrapper(*args, **kwargs) -> T:
            retry_config = config or RetryConfig()
            circuit_breaker = get_circuit_breaker(circuit_breaker_name) if circuit_breaker_name else None
            
            last_exception = None
            
            for attempt in range(1, retry_config.max_attempts + 1):
                try:
                    logger.debug(f"Attempt {attempt}/{retry_config.max_attempts} for {func.__name__}")
                    
                    if circuit_breaker:
                        result = await circuit_breaker.call(func, *args, **kwargs)
                    else:
                        result = await func(*args, **kwargs)
                    
                    logger.debug(f"Successfully executed {func.__name__} on attempt {attempt}")
                    return result
                    
                except expected_exceptions as e:
                    last_exception = e
                    logger.warning(f"Attempt {attempt} failed for {func.__name__}: {str(e)}")
                    
                    if attempt == retry_config.max_attempts:
                        break
                    
                    delay = calculate_delay(attempt, retry_config)
                    logger.debug(f"Retrying {func.__name__} in {delay:.2f} seconds")
                    await asyncio.sleep(delay)
            
            # All retries failed, try fallback
            if fallback_func:
                try:
                    logger.info(f"Using fallback for {func.__name__}")
                    return await fallback_func(*args, **kwargs) if asyncio.iscoroutinefunction(fallback_func) else fallback_func(*args, **kwargs)
                except Exception as fallback_error:
                    logger.error(f"Fallback also failed for {func.__name__}: {str(fallback_error)}")
            
            logger.error(f"All retries exhausted for {func.__name__}")
            raise last_exception
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs) -> T:
            retry_config = config or RetryConfig()
            last_exception = None
            
            for attempt in range(1, retry_config.max_attempts + 1):
                try:
                    logger.debug(f"Attempt {attempt}/{retry_config.max_attempts} for {func.__name__}")
                    result = func(*args, **kwargs)
                    logger.debug(f"Successfully executed {func.__name__} on attempt {attempt}")
                    return result
                    
                except expected_exceptions as e:
                    last_exception = e
                    logger.warning(f"Attempt {attempt} failed for {func.__name__}: {str(e)}")
                    
                    if attempt == retry_config.max_attempts:
                        break
                    
                    delay = calculate_delay(attempt, retry_config)
                    logger.debug(f"Retrying {func.__name__} in {delay:.2f} seconds")
                    time.sleep(delay)
            
            # Try fallback
            if fallback_func:
                try:
                    logger.info(f"Using fallback for {func.__name__}")
                    return fallback_func(*args, **kwargs)
                except Exception as fallback_error:
                    logger.error(f"Fallback also failed for {func.__name__}: {str(fallback_error)}")
            
            logger.error(f"All retries exhausted for {func.__name__}")
            raise last_exception
        
        # Return appropriate wrapper based on function type
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator

class HealthCheck:
    """Health check utility for external services"""
    
    def __init__(self):
        self.service_status: Dict[str, Dict] = {}
        
    async def check_http_service(self, name: str, url: str, timeout: int = 5) -> bool:
        """Check if HTTP service is healthy"""
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.get(url)
                healthy = response.status_code == 200
                
            self.service_status[name] = {
                'healthy': healthy,
                'last_check': datetime.now(),
                'response_code': response.status_code if 'response' in locals() else None
            }
            return healthy
            
        except Exception as e:
            logger.warning(f"Health check failed for {name}: {str(e)}")
            self.service_status[name] = {
                'healthy': False,
                'last_check': datetime.now(),
                'error': str(e)
            }
            return False
    
    def get_service_status(self, name: str) -> Dict:
        """Get status of a specific service"""
        return self.service_status.get(name, {'healthy': False, 'error': 'Not checked'})
    
    def get_all_status(self) -> Dict[str, Dict]:
        """Get status of all services"""
        return self.service_status.copy()

# Global health checker instance
health_checker = HealthCheck()

class FallbackCache:
    """Simple in-memory cache for fallback data"""
    
    def __init__(self, max_age: int = 3600):  # 1 hour default
        self.cache: Dict[str, Dict] = {}
        self.max_age = max_age
        
    def set(self, key: str, value: Any, ttl: Optional[int] = None):
        """Set cache value with TTL"""
        expiry = datetime.now() + timedelta(seconds=ttl or self.max_age)
        self.cache[key] = {
            'value': value,
            'expiry': expiry,
            'created': datetime.now()
        }
        
    def get(self, key: str) -> Optional[Any]:
        """Get cache value if not expired"""
        if key not in self.cache:
            return None
            
        entry = self.cache[key]
        if datetime.now() > entry['expiry']:
            del self.cache[key]
            return None
            
        return entry['value']
    
    def clear_expired(self):
        """Clear expired entries"""
        now = datetime.now()
        expired_keys = [k for k, v in self.cache.items() if now > v['expiry']]
        for key in expired_keys:
            del self.cache[key]
        logger.debug(f"Cleared {len(expired_keys)} expired cache entries")

# Global fallback cache instance
fallback_cache = FallbackCache()

# Rate limiters for different services
_rate_limiters: Dict[str, RateLimiter] = {
    'groq': RateLimiter(rate=2.0, burst=5),  # 2 requests per second
    'gecko': RateLimiter(rate=10.0, burst=20),  # 10 requests per second  
    'mcp': RateLimiter(rate=5.0, burst=10),  # 5 requests per second
}

def get_rate_limiter(service_name: str) -> RateLimiter:
    """Get rate limiter for a service"""
    return _rate_limiters.get(service_name, RateLimiter(rate=1.0, burst=5))

async def with_rate_limit(service_name: str, func: Callable, *args, **kwargs):
    """Execute function with rate limiting"""
    rate_limiter = get_rate_limiter(service_name)
    await rate_limiter.wait_for_token()
    return await func(*args, **kwargs) if asyncio.iscoroutinefunction(func) else func(*args, **kwargs)