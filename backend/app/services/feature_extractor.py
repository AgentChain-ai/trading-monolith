import os
import re
import math
import hashlib
import logging
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional, Tuple
from groq import Groq
from textblob import TextBlob
import json
from dataclasses import dataclass

from ..utils.resilience import (
    retry_with_fallback,
    RetryConfig,
    CircuitBreakerConfig,
    get_circuit_breaker,
    with_rate_limit,
    fallback_cache
)

logger = logging.getLogger(__name__)

@dataclass
class ArticleFeatures:
    """Container for extracted article features"""
    event_probs: Dict[str, float]
    sentiment_score: float
    source_trust: float
    recency_decay: float
    novelty_score: float
    proof_bonus: float
    final_weight: float

class FeatureExtractor:
    """Extract features from articles for ML model training and prediction"""
    
    # Event types for classification
    EVENT_TYPES = [
        "listing", "partnership", "hack", "depeg", "regulatory", 
        "funding", "tech", "market-note", "op-ed"
    ]
    
    # Source trust mapping
    SOURCE_TRUST_MAP = {
        # High trust - Official sources, major exchanges
        "coinbase.com": 1.2,
        "binance.com": 1.2,
        "kraken.com": 1.2,
        "coindesk.com": 1.1,
        "cointelegraph.com": 1.1,
        "decrypt.co": 1.1,
        "theblock.co": 1.1,
        
        # Medium trust - Established news
        "reuters.com": 1.0,
        "bloomberg.com": 1.0,
        "wsj.com": 1.0,
        "ft.com": 1.0,
        
        # Lower trust - Blogs, forums
        "medium.com": 0.8,
        "substack.com": 0.8,
        "reddit.com": 0.7,
        "twitter.com": 0.7,
        "x.com": 0.7,
        
        # Default for unknown sources
        "default": 0.6
    }
    
    def __init__(self):
        # Initialize Groq client
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise ValueError("GROQ_API_KEY environment variable is required")
        
        self.groq_client = Groq(api_key=api_key)
        self.model_name = os.getenv("MODEL_DRAFT", "llama-3.1-8b-instant")
        
        # Initialize circuit breaker for Groq API with adjusted parameters
        self.circuit_breaker = get_circuit_breaker(
            "groq_api",
            CircuitBreakerConfig(
                failure_threshold=5,  # Allow more failures before opening
                timeout=60,   # Shorter timeout - 1 minute
                expected_exception=(Exception,)  # Catch all Groq-related exceptions
            )
        )
        
        # Retry configuration for Groq API calls
        self.retry_config = RetryConfig(
            max_attempts=3,  # Increase attempts slightly
            base_delay=1.0,  # Faster initial retry
            max_delay=8.0,
            exponential_base=2.0,
            jitter=True
        )
        
        # Cache for content hashes to detect duplicates
        self.content_hashes = set()
        
        # Regex patterns for proof signals
        self.contract_patterns = [
            r'0x[a-fA-F0-9]{40}',  # Ethereum addresses
            r'contract[\s:]+0x[a-fA-F0-9]{40}',
            r'token[\s:]+0x[a-fA-F0-9]{40}',
        ]
        
        self.scanner_patterns = [
            r'etherscan\.io',
            r'bscscan\.com',
            r'polygonscan\.com',
            r'arbiscan\.io',
            r'ftmscan\.com'
        ]
        
    def _get_fallback_event_classification(self, title: str, content: str) -> Dict[str, float]:
        """Get cached or rule-based event classification as fallback"""
        # Create cache key from content hash
        content_to_hash = f"{title[:100]} {content[:500]}"
        cache_key = f"event_classification:{hashlib.md5(content_to_hash.encode()).hexdigest()}"
        
        # Check cache first
        cached_result = fallback_cache.get(cache_key)
        if cached_result:
            logger.info("Using cached event classification")
            return cached_result
        
        # Rule-based fallback classification
        text_lower = f"{title} {content}".lower()
        
        # Simple keyword-based classification
        classification_rules = {
            "listing": ["listing", "listed", "trading pair", "exchange", "available on"],
            "partnership": ["partnership", "partner", "collaboration", "integrate", "alliance"],
            "hack": ["hack", "exploit", "breach", "attack", "stolen", "drained"],
            "depeg": ["depeg", "peg", "stable", "unstable", "depegged"],
            "regulatory": ["regulation", "regulatory", "sec", "government", "legal", "compliance"],
            "funding": ["funding", "investment", "raised", "round", "capital", "investor"],
            "tech": ["update", "upgrade", "launch", "release", "technical", "development"],
            "market-note": ["price", "trading", "market", "analysis", "chart", "technical analysis"],
            "op-ed": ["opinion", "editorial", "commentary", "think", "believe", "analysis"]
        }
        
        scores = {}
        for event_type, keywords in classification_rules.items():
            score = sum(text_lower.count(keyword) for keyword in keywords)
            scores[event_type] = score
        
        # Normalize scores
        total_score = sum(scores.values())
        if total_score > 0:
            result = {k: v / total_score for k, v in scores.items()}
        else:
            # Default to market-note if no keywords match
            result = {event: 0.0 for event in self.EVENT_TYPES}
            result["market-note"] = 1.0
        
        # Cache the result
        fallback_cache.set(cache_key, result, ttl=3600)  # 1 hour
        logger.info("Using rule-based event classification fallback")
        
        return result
    
    async def extract_features(self, article_data: Dict[str, Any], token: str) -> ArticleFeatures:
        """
        Extract all features from an article
        
        Args:
            article_data: Raw article data from MCP scraping
            token: Token symbol being analyzed
            
        Returns:
            ArticleFeatures object with all extracted features
        """
        try:
            # Extract basic information
            title = article_data.get("title", "")
            content = article_data.get("clean_content", article_data.get("content", ""))
            site_name = article_data.get("site_name", "")
            published_at = article_data.get("published_at")
            url = article_data.get("url", "")
            
            # 1. Event Classification
            event_probs = await self._classify_event(title, content)
            
            # 2. Token-aware Sentiment Analysis
            sentiment_score = self._analyze_sentiment(title, content, token)
            
            # 3. Source Trust Score
            source_trust = self._get_source_trust(site_name, url)
            
            # 4. Recency Decay
            recency_decay = self._calculate_recency_decay(published_at)
            
            # 5. Novelty Score (duplicate detection)
            novelty_score = self._calculate_novelty(content)
            
            # 6. Proof Bonus (contract/scanner links)
            proof_bonus = self._detect_proof_signals(content, url)
            
            # 7. Final Weight Calculation
            final_weight = source_trust * recency_decay * novelty_score * proof_bonus
            
            return ArticleFeatures(
                event_probs=event_probs,
                sentiment_score=sentiment_score,
                source_trust=source_trust,
                recency_decay=recency_decay,
                novelty_score=novelty_score,
                proof_bonus=proof_bonus,
                final_weight=final_weight
            )
            
        except Exception as e:
            logger.error(f"Error extracting features: {e}")
            # Return default features on error
            return ArticleFeatures(
                event_probs={event: 0.0 for event in self.EVENT_TYPES},
                sentiment_score=0.0,
                source_trust=0.5,
                recency_decay=0.1,
                novelty_score=1.0,
                proof_bonus=1.0,
                final_weight=0.05
            )
    
    @retry_with_fallback(
        config=RetryConfig(max_attempts=2, base_delay=2.0, max_delay=8.0),
        circuit_breaker_name="groq_api",
        expected_exceptions=(Exception,)
    )
    async def _classify_event_with_retry(self, title: str, content: str) -> Dict[str, float]:
        """Internal event classification method with retry logic"""
        # Combine title and first part of content for classification
        text_to_classify = f"Title: {title}\n\nContent: {content[:1000]}..."
        
        # Create a cleaner, more focused prompt
        prompt = f"""Classify this crypto article into event types. Return ONLY valid JSON.

Article Title: {title[:200]}
Content: {content[:800]}

Event Types:
- listing: Exchange listings, new trading pairs
- partnership: Business partnerships, collaborations
- hack: Security breaches, exploits, stolen funds
- depeg: Stablecoin losing peg, price stability issues
- regulatory: Government regulations, legal news
- funding: Investment rounds, fundraising
- tech: Technical updates, upgrades, launches
- market-note: Market analysis, price movements
- op-ed: Opinion pieces, editorials

Return probabilities (0.0-1.0, must sum to 1.0) in this exact format:
{{"listing": 0.0, "partnership": 0.0, "hack": 0.0, "depeg": 0.0, "regulatory": 0.0, "funding": 0.0, "tech": 0.0, "market-note": 0.0, "op-ed": 0.0}}"""
        
        try:
            response = self.groq_client.chat.completions.create(
                model=self.model_name,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=300,  # Increase token limit slightly
                timeout=30  # Add timeout
            )
            
            # Parse the JSON response with better error handling
            result_text = response.choices[0].message.content
            if not result_text:
                raise ValueError("Empty response from Groq API")
                
            result_text = result_text.strip()
            logger.debug(f"Raw Groq response: {result_text[:200]}...")
            
            # Extract JSON from response with improved regex
            json_patterns = [
                r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}',  # Better nested JSON matching
                r'\{.*?"op-ed":\s*[\d.]+.*?\}',      # Look for the last key as anchor
                r'\{(?:[^{}]++|\{(?:[^{}]++|\{[^{}]*+\})*+\})*+\}'  # Recursive pattern
            ]
            
            parsed_json = None
            for pattern in json_patterns:
                json_matches = re.findall(pattern, result_text, re.DOTALL)
                if json_matches:
                    # Try each match until we find valid JSON
                    for match in json_matches:
                        try:
                            parsed_json = json.loads(match)
                            break
                        except json.JSONDecodeError:
                            continue
                    if parsed_json:
                        break
            
            if not parsed_json:
                # Try to parse the entire response as JSON
                try:
                    parsed_json = json.loads(result_text)
                except json.JSONDecodeError:
                    raise ValueError(f"No valid JSON found in response: {result_text}")
            
            # Validate response structure
            if not isinstance(parsed_json, dict):
                raise ValueError("Response is not a JSON object")
            
            # Check if all required event types are present
            missing_events = set(self.EVENT_TYPES) - set(parsed_json.keys())
            if missing_events:
                logger.warning(f"Missing event types in response: {missing_events}")
                # Add missing events with 0.0 probability
                for event in missing_events:
                    parsed_json[event] = 0.0
            
            # Remove any extra keys not in EVENT_TYPES
            event_probs = {k: v for k, v in parsed_json.items() if k in self.EVENT_TYPES}
            
            # Validate probability values
            for event, prob in event_probs.items():
                if not isinstance(prob, (int, float)) or prob < 0:
                    logger.warning(f"Invalid probability for {event}: {prob}, setting to 0.0")
                    event_probs[event] = 0.0
            
            # Normalize probabilities
            total_prob = sum(event_probs.values())
            if total_prob > 0:
                event_probs = {k: v/total_prob for k, v in event_probs.items()}
            else:
                # Default to market-note if all probabilities are 0
                event_probs = {event: 0.0 for event in self.EVENT_TYPES}
                event_probs["market-note"] = 1.0
                
        except Exception as api_error:
            logger.error(f"Groq API call failed: {api_error}")
            # Re-raise to be caught by retry mechanism
            raise api_error
        
        # Cache successful result
        content_to_hash = f"{title[:100]} {content[:500]}"
        cache_key = f"event_classification:{hashlib.md5(content_to_hash.encode()).hexdigest()}"
        fallback_cache.set(cache_key, event_probs, ttl=3600)  # 1 hour
        
        return event_probs
    
    async def _classify_event(self, title: str, content: str) -> Dict[str, float]:
        """Classify the event type using Groq LLM with resilience features"""
        try:
            # Check for empty or very short content first
            if not title and not content:
                logger.warning("Empty title and content, using fallback classification")
                return self._get_fallback_event_classification("", "")
            
            if len(title + content) < 50:
                logger.warning("Very short content, using fallback classification")
                return self._get_fallback_event_classification(title, content)
            
            # Apply rate limiting and circuit breaker
            return await with_rate_limit("groq", self._classify_event_with_retry, title, content)
            
        except Exception as e:
            logger.error(f"Event classification failed: {e}")
            
            # Try fallback classification first (more reliable than uniform)
            try:
                fallback_result = self._get_fallback_event_classification(title, content)
                if fallback_result and sum(fallback_result.values()) > 0:
                    logger.info("Using rule-based fallback classification")
                    return fallback_result
            except Exception as fallback_error:
                logger.error(f"Fallback classification also failed: {fallback_error}")
            
            # Final fallback: intelligent default based on content keywords
            logger.warning("Using intelligent default classification")
            return self._get_intelligent_default_classification(title, content)
    
    def _get_intelligent_default_classification(self, title: str, content: str) -> Dict[str, float]:
        """Get an intelligent default classification based on simple heuristics"""
        text = f"{title} {content}".lower()
        
        # Simple heuristics for better defaults than uniform distribution
        if any(word in text for word in ["price", "trading", "chart", "analysis", "market"]):
            return {event: 0.0 if event != "market-note" else 1.0 for event in self.EVENT_TYPES}
        elif any(word in text for word in ["hack", "exploit", "breach", "stolen"]):
            return {event: 0.0 if event != "hack" else 1.0 for event in self.EVENT_TYPES}
        elif any(word in text for word in ["partnership", "partner", "collaboration"]):
            return {event: 0.0 if event != "partnership" else 1.0 for event in self.EVENT_TYPES}
        elif any(word in text for word in ["listing", "exchange", "trading pair"]):
            return {event: 0.0 if event != "listing" else 1.0 for event in self.EVENT_TYPES}
        else:
            # Default to market-note for unknown content
            return {event: 0.0 if event != "market-note" else 1.0 for event in self.EVENT_TYPES}
    
    def _analyze_sentiment(self, title: str, content: str, token: str) -> float:
        """Analyze token-aware sentiment"""
        try:
            # Focus on paragraphs mentioning the token
            token_mentions = []
            
            # Check title (weight 2x)
            if token.lower() in title.lower():
                token_mentions.append(title)
                token_mentions.append(title)  # Add twice for 2x weight
            
            # Find paragraphs with token mentions
            paragraphs = content.split('\n')
            for para in paragraphs:
                if token.lower() in para.lower() and len(para.strip()) > 50:
                    token_mentions.append(para.strip())
            
            # If no specific mentions, use first 500 chars
            if not token_mentions:
                token_mentions = [content[:500]]
            
            # Analyze sentiment of relevant text
            sentiment_scores = []
            for text in token_mentions:
                if text.strip():
                    blob = TextBlob(text)
                    sentiment_scores.append(blob.sentiment.polarity)
            
            if sentiment_scores:
                return sum(sentiment_scores) / len(sentiment_scores)
            else:
                return 0.0
                
        except Exception as e:
            logger.error(f"Error in sentiment analysis: {e}")
            return 0.0
    
    def _get_source_trust(self, site_name: str, url: str) -> float:
        """Get source trust score based on domain"""
        try:
            # Extract domain from site_name or URL
            domain = site_name.lower() if site_name else ""
            
            if not domain and url:
                # Extract domain from URL
                import urllib.parse
                parsed = urllib.parse.urlparse(url)
                domain = parsed.netloc.lower()
            
            # Remove www. prefix
            domain = domain.replace("www.", "")
            
            # Look up trust score
            return self.SOURCE_TRUST_MAP.get(domain, self.SOURCE_TRUST_MAP["default"])
            
        except Exception as e:
            logger.error(f"Error getting source trust: {e}")
            return self.SOURCE_TRUST_MAP["default"]
    
    def _calculate_recency_decay(self, published_at: Optional[str], tau_hours: float = 12.0) -> float:
        """Calculate recency decay: exp(-Δt_hours / τ)"""
        try:
            if not published_at:
                # If no publish date, assume very recent
                return 1.0
            
            # Parse the published date
            if isinstance(published_at, str):
                # Try different date formats
                for fmt in ["%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"]:
                    try:
                        pub_dt = datetime.strptime(published_at.replace('Z', '+00:00'), fmt)
                        if pub_dt.tzinfo is None:
                            pub_dt = pub_dt.replace(tzinfo=timezone.utc)
                        break
                    except ValueError:
                        continue
                else:
                    # If parsing fails, assume recent
                    return 0.8
            else:
                pub_dt = published_at
            
            # Calculate hours since publication
            now = datetime.now(timezone.utc)
            delta_hours = (now - pub_dt).total_seconds() / 3600
            
            # Apply exponential decay
            decay = math.exp(-delta_hours / tau_hours)
            return max(0.01, min(1.0, decay))  # Clamp between 0.01 and 1.0
            
        except Exception as e:
            logger.error(f"Error calculating recency decay: {e}")
            return 0.5  # Default moderate decay
    
    def _calculate_novelty(self, content: str) -> float:
        """Calculate novelty score using content hashing"""
        try:
            if not content or len(content) < 100:
                return 0.5  # Short content gets moderate novelty
            
            # Create a hash of the content
            content_hash = hashlib.md5(content.encode()).hexdigest()
            
            # Check if we've seen this content before
            if content_hash in self.content_hashes:
                return 0.0  # Duplicate content
            else:
                self.content_hashes.add(content_hash)
                return 1.0  # Novel content
                
        except Exception as e:
            logger.error(f"Error calculating novelty: {e}")
            return 1.0  # Default to novel on error
    
    def _detect_proof_signals(self, content: str, url: str) -> float:
        """Detect proof signals (contract addresses, scanner links)"""
        try:
            text_to_check = f"{content} {url}".lower()
            
            # Check for contract addresses
            for pattern in self.contract_patterns:
                if re.search(pattern, text_to_check, re.IGNORECASE):
                    return 1.1  # 10% bonus
            
            # Check for blockchain scanner links
            for pattern in self.scanner_patterns:
                if re.search(pattern, text_to_check, re.IGNORECASE):
                    return 1.1  # 10% bonus
            
            return 1.0  # No bonus
            
        except Exception as e:
            logger.error(f"Error detecting proof signals: {e}")
            return 1.0
    
    def clear_novelty_cache(self):
        """Clear the novelty detection cache"""
        self.content_hashes.clear()
        logger.info("Novelty cache cleared")