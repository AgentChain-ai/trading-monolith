import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Any, Optional, Tuple
from collections import defaultdict
from sqlalchemy.orm import Session
import statistics
import math

from ..models import Article, Bucket
from ..database import SessionLocal

logger = logging.getLogger(__name__)

class NarrativeAggregator:
    """Aggregate article features into bucket-level narrative metrics"""
    
    def __init__(self, bucket_window_minutes: int = 10):
        self.bucket_window_minutes = bucket_window_minutes
        self.event_types = [
            "listing", "partnership", "hack", "depeg", "regulatory", 
            "funding", "tech", "market-note", "op-ed"
        ]
        self.risk_events = ["hack", "depeg", "regulatory"]
        
    async def aggregate_token_bucket(
        self, 
        token: str, 
        bucket_ts: datetime, 
        articles: List[Article]
    ) -> Dict[str, Any]:
        """
        Aggregate article features into bucket-level metrics
        
        Args:
            token: Token symbol
            bucket_ts: Bucket timestamp
            articles: List of articles in this bucket
            
        Returns:
            Dictionary with aggregated bucket features
        """
        try:
            if not articles:
                return self._get_empty_bucket_features()
            
            # Calculate Narrative Heat (NHS)
            narrative_heat = self._calculate_narrative_heat(articles)
            
            # Calculate positive and negative heat
            positive_heat, negative_heat = self._calculate_sentiment_heat(articles)
            
            # Calculate event consensus and distribution
            consensus, event_distribution, top_event = self._calculate_event_consensus(articles)
            
            # Calculate risk polarity
            risk_polarity = self._calculate_risk_polarity(event_distribution, articles)
            
            # Calculate hype velocity (requires previous bucket)
            hype_velocity = await self._calculate_hype_velocity(token, bucket_ts, narrative_heat)
            
            return {
                'narrative_heat': narrative_heat,
                'positive_heat': positive_heat,
                'negative_heat': negative_heat,
                'consensus': consensus,
                'hype_velocity': hype_velocity,
                'risk_polarity': risk_polarity,
                'event_distribution': event_distribution,
                'top_event': top_event,
                'article_count': len(articles),
                'avg_source_trust': statistics.mean([a.source_trust or 0.5 for a in articles]),
                'avg_novelty': statistics.mean([a.novelty_score or 0.5 for a in articles]),
            }
            
        except Exception as e:
            logger.error(f"Error aggregating bucket for {token}: {e}")
            return self._get_empty_bucket_features()
    
    def _calculate_narrative_heat(self, articles: List[Article]) -> float:
        """
        Calculate Narrative Heat Score (NHS)
        NHS_t = Σ (sentiment_score * final_weight)
        """
        try:
            total_heat = 0.0
            
            for article in articles:
                sentiment = article.sentiment_score or 0.0
                weight = article.final_weight or 0.0
                contribution = sentiment * weight
                total_heat += contribution
            
            return round(total_heat, 3)
            
        except Exception as e:
            logger.error(f"Error calculating narrative heat: {e}")
            return 0.0
    
    def _calculate_sentiment_heat(self, articles: List[Article]) -> Tuple[float, float]:
        """Calculate positive and negative heat separately"""
        try:
            positive_heat = 0.0
            negative_heat = 0.0
            
            for article in articles:
                sentiment = article.sentiment_score or 0.0
                weight = article.final_weight or 0.0
                contribution = sentiment * weight
                
                if contribution > 0:
                    positive_heat += contribution
                else:
                    negative_heat += abs(contribution)
            
            return round(positive_heat, 3), round(negative_heat, 3)
            
        except Exception as e:
            logger.error(f"Error calculating sentiment heat: {e}")
            return 0.0, 0.0
    
    def _calculate_event_consensus(self, articles: List[Article]) -> Tuple[float, Dict[str, float], str]:
        """
        Calculate event consensus and distribution
        Returns: (consensus_score, event_distribution, top_event)
        """
        try:
            if not articles:
                return 0.0, {}, "unknown"
            
            # Collect event probabilities weighted by article weight
            weighted_event_scores = defaultdict(float)
            total_weight = 0.0
            
            for article in articles:
                weight = article.final_weight or 0.0
                event_probs = article.event_probs or {}
                
                for event_type in self.event_types:
                    prob = event_probs.get(event_type, 0.0)
                    weighted_event_scores[event_type] += prob * weight
                
                total_weight += weight
            
            if total_weight == 0:
                return 0.0, {}, "unknown"
            
            # Normalize by total weight to get distribution
            event_distribution = {}
            for event_type in self.event_types:
                event_distribution[event_type] = weighted_event_scores[event_type] / total_weight
            
            # Find top event
            top_event = max(event_distribution, key=event_distribution.get)
            top_event_prob = event_distribution[top_event]
            
            # Calculate consensus as the fraction agreeing with top event
            # This is the probability mass concentrated in the top event
            consensus = top_event_prob
            
            return round(consensus, 3), event_distribution, top_event
            
        except Exception as e:
            logger.error(f"Error calculating event consensus: {e}")
            return 0.0, {}, "unknown"
    
    def _calculate_risk_polarity(self, event_distribution: Dict[str, float], articles: List[Article]) -> float:
        """
        Calculate risk polarity
        Negative if risk events (hack/regulatory/depeg) dominate
        """
        try:
            # Sum probabilities of risk events
            risk_prob = sum(event_distribution.get(event, 0.0) for event in self.risk_events)
            
            # Sum probabilities of positive events  
            positive_events = ["listing", "partnership", "funding", "tech"]
            positive_prob = sum(event_distribution.get(event, 0.0) for event in positive_events)
            
            # Calculate polarity: positive_prob - risk_prob
            # Range: [-1, 1] where negative means risk dominates
            polarity = positive_prob - risk_prob
            
            # Weight by overall narrative strength
            avg_weight = statistics.mean([a.final_weight or 0.0 for a in articles]) if articles else 0.0
            weighted_polarity = polarity * min(avg_weight, 1.0)
            
            return round(weighted_polarity, 3)
            
        except Exception as e:
            logger.error(f"Error calculating risk polarity: {e}")
            return 0.0
    
    async def _calculate_hype_velocity(self, token: str, current_bucket_ts: datetime, current_heat: float) -> float:
        """
        Calculate hype velocity: (NHS_t - NHS_{t-1}) / max(|NHS_{t-1}|, 1)
        """
        try:
            db = SessionLocal()
            try:
                # Get previous bucket
                previous_bucket = db.query(Bucket).filter(
                    Bucket.token == token,
                    Bucket.bucket_ts < current_bucket_ts
                ).order_by(Bucket.bucket_ts.desc()).first()
                
                if not previous_bucket or previous_bucket.narrative_heat is None:
                    return 0.0  # No previous data
                
                previous_heat = previous_bucket.narrative_heat
                
                # Calculate velocity
                denominator = max(abs(previous_heat), 1.0)
                velocity = (current_heat - previous_heat) / denominator
                
                return round(velocity, 3)
                
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"Error calculating hype velocity: {e}")
            return 0.0
    
    def _get_empty_bucket_features(self) -> Dict[str, Any]:
        """Return default features for empty buckets"""
        return {
            'narrative_heat': 0.0,
            'positive_heat': 0.0,
            'negative_heat': 0.0,
            'consensus': 0.0,
            'hype_velocity': 0.0,
            'risk_polarity': 0.0,
            'event_distribution': {event: 0.0 for event in self.event_types},
            'top_event': 'unknown',
            'article_count': 0,
            'avg_source_trust': 0.5,
            'avg_novelty': 0.5,
        }
    
    async def create_or_update_bucket(
        self, 
        token: str, 
        articles: List[Article],
        bucket_ts: Optional[datetime] = None
    ) -> Bucket:
        """
        Create or update a bucket with aggregated features
        
        Args:
            token: Token symbol
            articles: Articles to aggregate
            bucket_ts: Optional bucket timestamp (defaults to current time bucketed)
            
        Returns:
            Created or updated Bucket object
        """
        try:
            if bucket_ts is None:
                bucket_ts = self._get_bucket_timestamp(datetime.utcnow())
            
            # Calculate aggregated features
            features = await self.aggregate_token_bucket(token, bucket_ts, articles)
            
            db = SessionLocal()
            try:
                # Check if bucket already exists
                existing_bucket = db.query(Bucket).filter(
                    Bucket.token == token,
                    Bucket.bucket_ts == bucket_ts
                ).first()
                
                if existing_bucket:
                    # Update existing bucket
                    for key, value in features.items():
                        if hasattr(existing_bucket, key):
                            setattr(existing_bucket, key, value)
                    bucket = existing_bucket
                else:
                    # Filter features to only include valid Bucket fields
                    bucket_features = {}
                    bucket_fields = [
                        'narrative_heat', 'positive_heat', 'negative_heat', 'consensus',
                        'hype_velocity', 'risk_polarity', 'event_distribution', 'top_event',
                        'liquidity_usd', 'trades_count_change', 'spread_estimate',
                        'article_count', 'avg_source_trust', 'avg_novelty'
                    ]
                    
                    for key, value in features.items():
                        if key in bucket_fields:
                            bucket_features[key] = value
                    
                    # Create new bucket
                    bucket = Bucket(
                        token=token,
                        bucket_ts=bucket_ts,
                        **bucket_features
                    )
                    db.add(bucket)
                
                db.commit()
                db.refresh(bucket)
                
                logger.info(f"Updated bucket for {token} at {bucket_ts}: NHS={features['narrative_heat']:.2f}")
                return bucket
                
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"Error creating/updating bucket: {e}")
            raise
    
    def _get_bucket_timestamp(self, timestamp: datetime) -> datetime:
        """
        Round timestamp down to nearest bucket window
        
        Args:
            timestamp: Input timestamp
            
        Returns:
            Bucketed timestamp
        """
        # Round down to nearest bucket_window_minutes
        minutes = timestamp.minute
        bucketed_minutes = (minutes // self.bucket_window_minutes) * self.bucket_window_minutes
        
        return timestamp.replace(
            minute=bucketed_minutes,
            second=0,
            microsecond=0
        )
    
    async def process_token_articles(self, token: str, hours_back: int = 2) -> List[Bucket]:
        """
        Process all recent articles for a token and create/update buckets
        
        Args:
            token: Token symbol  
            hours_back: How many hours back to process
            
        Returns:
            List of created/updated buckets
        """
        try:
            db = SessionLocal()
            try:
                # Get recent articles
                since = datetime.utcnow() - timedelta(hours=hours_back)
                articles = db.query(Article).filter(
                    Article.token == token,
                    Article.created_at >= since,
                    Article.final_weight.isnot(None)
                ).order_by(Article.created_at).all()
                
                if not articles:
                    logger.info(f"No articles found for {token} in last {hours_back} hours")
                    return []
                
                # Group articles by bucket
                bucket_articles = defaultdict(list)
                for article in articles:
                    if article.bucket_ts:
                        bucket_articles[article.bucket_ts].append(article)
                    else:
                        # Assign bucket timestamp if not set
                        bucket_ts = self._get_bucket_timestamp(article.created_at)
                        article.bucket_ts = bucket_ts
                        bucket_articles[bucket_ts].append(article)
                
                # Update articles with bucket_ts
                db.commit()
                
                # Process each bucket
                buckets = []
                for bucket_ts, bucket_articles_list in bucket_articles.items():
                    bucket = await self.create_or_update_bucket(
                        token, bucket_articles_list, bucket_ts
                    )
                    buckets.append(bucket)
                
                logger.info(f"Processed {len(buckets)} buckets for {token}")
                return sorted(buckets, key=lambda x: x.bucket_ts)
                
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"Error processing articles for {token}: {e}")
            return []
    
    async def get_latest_bucket(self, token: str) -> Optional[Bucket]:
        """Get the most recent bucket for a token"""
        db = SessionLocal()
        try:
            bucket = db.query(Bucket).filter(
                Bucket.token == token
            ).order_by(Bucket.bucket_ts.desc()).first()
            
            return bucket
            
        finally:
            db.close()
    
    async def get_token_buckets(self, token: str, hours_back: int = 24) -> List[Bucket]:
        """Get recent buckets for a token"""
        db = SessionLocal()
        try:
            since = datetime.utcnow() - timedelta(hours=hours_back)
            buckets = db.query(Bucket).filter(
                Bucket.token == token,
                Bucket.bucket_ts >= since
            ).order_by(Bucket.bucket_ts).all()
            
            return buckets
            
        finally:
            db.close()