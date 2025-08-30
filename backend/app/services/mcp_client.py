import httpx
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
import asyncio
from pydantic import BaseModel
import json

from ..utils.resilience import (
    retry_with_fallback,
    RetryConfig,
    CircuitBreakerConfig,
    get_circuit_breaker,
    with_rate_limit,
    health_checker,
    fallback_cache,
    calculate_delay
)

logger = logging.getLogger(__name__)

class SearchResult(BaseModel):
    content: str
    engine: str
    score: float
    title: str
    url: str

class ScrapeResult(BaseModel):
    author: Optional[str] = None
    canonical_url: Optional[str] = None
    clean_content: Optional[str] = None
    content: Optional[str] = None
    content_type: Optional[str] = None
    headings: List[Dict[str, str]] = []
    images: List[Dict[str, str]] = []
    language: Optional[str] = None
    links: List[Dict[str, str]] = []
    meta_description: Optional[str] = None
    meta_keywords: Optional[str] = None
    og_description: Optional[str] = None
    og_image: Optional[str] = None
    og_title: Optional[str] = None
    published_at: Optional[str] = None
    reading_time_minutes: Optional[int] = None
    site_name: Optional[str] = None
    status_code: Optional[int] = None
    timestamp: Optional[str] = None
    title: Optional[str] = None
    url: Optional[str] = None
    word_count: Optional[int] = None

class ChatResult(BaseModel):
    response: str
    scraped_content: List[ScrapeResult] = []
    search_results: List[SearchResult] = []

class MCPClient:
    """Client for interacting with Search-Scrape MCP Server API with resilience features"""
    
    def __init__(self, base_url: str = "https://scraper.agentchain.trade/"):
        self.base_url = base_url.rstrip('/')
        self.search_timeout = 30.0  # Fast operations
        self.scrape_timeout = 90.0  # Slow operations that return large data
        
        # Initialize separate circuit breakers for different operations
        self.search_circuit_breaker = get_circuit_breaker(
            "mcp_search",
            CircuitBreakerConfig(
                failure_threshold=5,
                timeout=60,  # 1 minute
                expected_exception=(httpx.HTTPError, httpx.ConnectError, httpx.TimeoutException)
            )
        )
        
        self.scrape_circuit_breaker = get_circuit_breaker(
            "mcp_scrape",
            CircuitBreakerConfig(
                failure_threshold=8,  # More tolerant for slow scrape operations
                timeout=180,  # 3 minutes
                expected_exception=(httpx.HTTPError, httpx.ConnectError, httpx.TimeoutException)
            )
        )
        
        # Retry configuration for MCP operations
        self.search_retry_config = RetryConfig(
            max_attempts=3,
            base_delay=1.0,
            max_delay=5.0,
            exponential_base=2.0,
            jitter=True
        )
        
        self.scrape_retry_config = RetryConfig(
            max_attempts=2,  # Fewer retries for slow operations
            base_delay=2.0,
            max_delay=15.0,
            exponential_base=2.0,
            jitter=True
        )
        
    async def health_check(self) -> bool:
        """Check if the MCP server is healthy with circuit breaker protection"""
        try:
            return await health_checker.check_http_service("mcp_server", f"{self.base_url}/health", timeout=5)
        except Exception as e:
            logger.error(f"MCP health check failed: {e}")
            return False
    
    def _get_fallback_search_results(self, query: str) -> List[SearchResult]:
        """Get cached search results as fallback"""
        cache_key = f"search_results:{query}"
        cached_results = fallback_cache.get(cache_key)
        if cached_results:
            logger.info(f"Using cached search results for query: {query}")
            return [SearchResult(**result) for result in cached_results]
        return []
    
    def _get_fallback_scrape_result(self, url: str) -> Optional[ScrapeResult]:
        """Get cached scrape result as fallback"""
        cache_key = f"scrape_result:{url}"
        cached_result = fallback_cache.get(cache_key)
        if cached_result:
            logger.info(f"Using cached scrape result for URL: {url}")
            return ScrapeResult(**cached_result)
        return None
    
    async def _search_with_retry(self, query: str) -> List[SearchResult]:
        """Internal search method with retry logic"""
        async with httpx.AsyncClient(timeout=self.search_timeout) as client:
            response = await client.post(
                f"{self.base_url}/search",
                json={"query": query},
                headers={"accept": "application/json"}
            )
            response.raise_for_status()
            
            data = response.json()
            results = data.get("results", [])
            
            # Cache successful results
            cache_key = f"search_results:{query}"
            fallback_cache.set(cache_key, results, ttl=1800)  # 30 minutes
            
            return [SearchResult(**result) for result in results]
    
    async def search(self, query: str) -> List[SearchResult]:
        """
        Search for content using the MCP server with resilience features
        
        Args:
            query: Search query (e.g., "twitter trends usdc token")
            
        Returns:
            List of search results
        """
        for attempt in range(1, self.search_retry_config.max_attempts + 1):
            try:
                logger.debug(f"Search attempt {attempt}/{self.search_retry_config.max_attempts} for query: {query}")
                
                # Apply rate limiting and circuit breaker
                result = await with_rate_limit("mcp", self.search_circuit_breaker.call, self._search_with_retry, query)
                logger.info(f"Search successful for query: {query}")
                return result
                
            except Exception as e:
                logger.warning(f"Search attempt {attempt} failed for query '{query}': {e}")
                
                if attempt < self.search_retry_config.max_attempts:
                    delay = calculate_delay(attempt, self.search_retry_config)
                    logger.debug(f"Retrying search in {delay:.2f} seconds")
                    await asyncio.sleep(delay)
                    continue
        
        # All retries failed, try fallback from cache
        logger.error(f"All search attempts failed for query: {query}")
        fallback_results = self._get_fallback_search_results(query)
        if fallback_results:
            logger.info(f"Using cached search results for query: {query}")
            return fallback_results
            
        # Return empty list if all else fails
        logger.warning(f"No fallback available for search query: {query}")
        return []
    
    async def _scrape_with_retry(self, url: str) -> ScrapeResult:
        """Internal scrape method with retry logic"""
        logger.info(f"Starting scrape for URL: {url}")
        
        async with httpx.AsyncClient(timeout=self.scrape_timeout) as client:
            response = await client.post(
                f"{self.base_url}/scrape",
                json={"url": url},
                headers={"accept": "application/json"}
            )
            response.raise_for_status()
            
            data = response.json()
            result = ScrapeResult(**data)
            
            # Cache successful results
            cache_key = f"scrape_result:{url}"
            fallback_cache.set(cache_key, data, ttl=3600)  # 1 hour
            
            logger.info(f"Scrape successful for URL: {url} (content length: {len(data.get('content', ''))}, response size: {len(str(data))} chars)")
            return result
    
    async def scrape(self, url: str) -> Optional[ScrapeResult]:
        """
        Scrape content from a URL using the MCP server with resilience features
        
        Args:
            url: URL to scrape
            
        Returns:
            Scraped content or None if failed
        """
        for attempt in range(1, self.scrape_retry_config.max_attempts + 1):
            try:
                logger.debug(f"Scrape attempt {attempt}/{self.scrape_retry_config.max_attempts} for URL: {url}")
                
                # Apply rate limiting and circuit breaker
                result = await with_rate_limit("mcp", self.scrape_circuit_breaker.call, self._scrape_with_retry, url)
                return result
                
            except Exception as e:
                logger.warning(f"Scrape attempt {attempt} failed for URL '{url}': {e}")
                
                if attempt < self.scrape_retry_config.max_attempts:
                    delay = calculate_delay(attempt, self.scrape_retry_config)
                    logger.debug(f"Retrying scrape in {delay:.2f} seconds")
                    await asyncio.sleep(delay)
                    continue
        
        # All retries failed, try fallback from cache
        logger.error(f"All scrape attempts failed for URL: {url}")
        fallback_result = self._get_fallback_scrape_result(url)
        if fallback_result:
            logger.info(f"Using cached scrape result for URL: {url}")
            return fallback_result
            
        # Return None if all else fails
        logger.warning(f"No fallback available for URL: {url}")
        return None
    
    async def _chat_with_retry(self, query: str) -> ChatResult:
        """Internal chat method with retry logic"""
        async with httpx.AsyncClient(timeout=self.scrape_timeout) as client:  # Chat may involve scraping, so use scrape timeout
            response = await client.post(
                f"{self.base_url}/chat",
                json={"query": query},
                headers={"accept": "application/json"}
            )
            response.raise_for_status()
            
            data = response.json()
            
            # Parse scraped content
            scraped_content = [
                ScrapeResult(**item) for item in data.get("scraped_content", [])
            ]
            
            # Parse search results
            search_results = [
                SearchResult(**item) for item in data.get("search_results", [])
            ]
            
            result = ChatResult(
                response=data.get("response", ""),
                scraped_content=scraped_content,
                search_results=search_results
            )
            
            # Cache successful results
            cache_key = f"chat_result:{query}"
            fallback_cache.set(cache_key, data, ttl=1800)  # 30 minutes
            
            return result
    
    def _get_fallback_chat_result(self, query: str) -> Optional[ChatResult]:
        """Get cached chat result as fallback"""
        cache_key = f"chat_result:{query}"
        cached_result = fallback_cache.get(cache_key)
        if cached_result:
            logger.info(f"Using cached chat result for query: {query}")
            
            # Parse cached data
            scraped_content = [
                ScrapeResult(**item) for item in cached_result.get("scraped_content", [])
            ]
            search_results = [
                SearchResult(**item) for item in cached_result.get("search_results", [])
            ]
            
            return ChatResult(
                response=cached_result.get("response", ""),
                scraped_content=scraped_content,
                search_results=search_results
            )
        return None
    
    async def chat(self, query: str) -> Optional[ChatResult]:
        """
        Get AI-powered chat response with search and scrape results
        
        Args:
            query: Chat query (e.g., "What are the latest Twitter trends about USDC token?")
            
        Returns:
            Chat result with response and supporting data
        """
        for attempt in range(1, self.scrape_retry_config.max_attempts + 1):  # Chat uses scrape-like retry config
            try:
                logger.debug(f"Chat attempt {attempt}/{self.scrape_retry_config.max_attempts} for query: {query}")
                
                # Apply rate limiting and circuit breaker (use scrape circuit breaker since chat may involve scraping)
                result = await with_rate_limit("mcp", self.scrape_circuit_breaker.call, self._chat_with_retry, query)
                return result
                
            except Exception as e:
                logger.warning(f"Chat attempt {attempt} failed for query '{query}': {e}")
                
                if attempt < self.scrape_retry_config.max_attempts:
                    delay = calculate_delay(attempt, self.scrape_retry_config)
                    logger.debug(f"Retrying chat in {delay:.2f} seconds")
                    await asyncio.sleep(delay)
                    continue
        
        # All retries failed, try fallback from cache
        logger.error(f"All chat attempts failed for query: {query}")
        fallback_result = self._get_fallback_chat_result(query)
        if fallback_result:
            logger.info(f"Using cached chat result for query: {query}")
            return fallback_result
        
        # Return None if all else fails
        logger.warning(f"No fallback available for chat query: {query}")
        return None
    
    async def search_and_scrape(self, query: str, max_articles: int = 10) -> List[ScrapeResult]:
        """
        Combined search and scrape operation
        
        Args:
            query: Search query
            max_articles: Maximum number of articles to scrape
            
        Returns:
            List of scraped articles
        """
        # First, search for articles
        search_results = await self.search(query)
        
        if not search_results:
            logger.warning(f"No search results for query: {query}")
            return []
        
        # Limit the number of articles to scrape
        urls_to_scrape = [result.url for result in search_results[:max_articles]]
        
        # Scrape articles concurrently
        scrape_tasks = [self.scrape(url) for url in urls_to_scrape]
        scraped_results = await asyncio.gather(*scrape_tasks, return_exceptions=True)
        
        # Filter out None results and exceptions
        valid_results = []
        for result in scraped_results:
            if isinstance(result, ScrapeResult):
                valid_results.append(result)
            elif isinstance(result, Exception):
                logger.error(f"Scraping error: {result}")
        
        logger.info(f"Successfully scraped {len(valid_results)} articles from {len(search_results)} search results")
        return valid_results
    
    async def get_token_articles(self, token: str, hours_back: int = 24, max_articles: int = 20) -> List[ScrapeResult]:
        """
        Get articles about a specific token
        
        Args:
            token: Token symbol (e.g., "USDC", "BTC")
            hours_back: How many hours back to search
            max_articles: Maximum articles to return
            
        Returns:
            List of scraped articles about the token
        """
        # Create comprehensive search queries
        queries = [
            f"{token} token news",
            f"{token} cryptocurrency latest",
            f"{token} twitter trends",
            f"{token} market analysis"
        ]
        
        all_articles = []
        
        # Search with different queries to get diverse results
        for query in queries:
            try:
                articles = await self.search_and_scrape(query, max_articles // len(queries))
                all_articles.extend(articles)
            except Exception as e:
                logger.error(f"Error searching for '{query}': {e}")
        
        # Remove duplicates based on URL
        seen_urls = set()
        unique_articles = []
        
        for article in all_articles:
            if article.url and article.url not in seen_urls:
                seen_urls.add(article.url)
                unique_articles.append(article)
        
        # Sort by relevance/recency if possible
        unique_articles = sorted(
            unique_articles,
            key=lambda x: x.published_at or x.timestamp or "",
            reverse=True
        )
        
        return unique_articles[:max_articles]