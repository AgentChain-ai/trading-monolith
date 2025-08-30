import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from sqlalchemy.orm import Session

from ..models import Article, Bucket
from ..database import SessionLocal
from .ml_engine import PredictionResult

logger = logging.getLogger(__name__)

@dataclass
class EvidenceItem:
    """Container for evidence supporting a thesis"""
    title: str
    url: str
    weight: float
    event_type: str
    sentiment: float

@dataclass
class TradingThesis:
    """Container for complete trading thesis"""
    token: str
    timestamp: str
    window_minutes: int
    narrative_heat: float
    consensus: float
    top_event: str
    p_up_60m: float
    confidence: str
    hype_velocity: float
    risk_polarity: float
    reasoning: List[str]
    guardrails: List[str]
    evidence: List[EvidenceItem]
    features_snapshot: Dict[str, float]

class ThesisComposer:
    """Compose trading theses from ML predictions and narrative analysis"""
    
    def __init__(self):
        self.confidence_thresholds = {
            "HIGH": 0.65,
            "MEDIUM": 0.45,
            "LOW": 0.0
        }
        
        self.risk_events = ["hack", "depeg", "regulatory"]
        self.positive_events = ["listing", "partnership", "funding", "tech"]
        
    async def compose_thesis(
        self, 
        token: str, 
        bucket_data: Dict[str, Any], 
        prediction: PredictionResult,
        window_minutes: int = 60
    ) -> TradingThesis:
        """
        Compose a complete trading thesis
        
        Args:
            token: Token symbol
            bucket_data: Latest bucket data with aggregated features
            prediction: ML prediction result
            window_minutes: Prediction window in minutes
            
        Returns:
            Complete TradingThesis object
        """
        try:
            # Extract key metrics with None safety
            narrative_heat = bucket_data.get('narrative_heat') or 0.0
            consensus = bucket_data.get('consensus') or 0.0
            hype_velocity = bucket_data.get('hype_velocity') or 0.0
            risk_polarity = bucket_data.get('risk_polarity') or 0.0
            top_event = bucket_data.get('top_event') or 'market-note'
            
            # Generate reasoning
            reasoning = self._generate_reasoning(
                token, bucket_data, prediction, narrative_heat, consensus, hype_velocity
            )
            
            # Generate guardrails
            guardrails = self._generate_guardrails(
                consensus, risk_polarity, narrative_heat, top_event
            )
            
            # Get supporting evidence
            evidence = await self._get_evidence(token, bucket_data.get('bucket_ts'))
            
            # Create thesis
            thesis = TradingThesis(
                token=token,
                timestamp=datetime.utcnow().isoformat(),
                window_minutes=window_minutes,
                narrative_heat=narrative_heat,
                consensus=consensus,
                top_event=top_event,
                p_up_60m=prediction.probability_up,
                confidence=prediction.confidence,
                hype_velocity=hype_velocity,
                risk_polarity=risk_polarity,
                reasoning=reasoning,
                guardrails=guardrails,
                evidence=evidence,
                features_snapshot=prediction.features_used
            )
            
            return thesis
            
        except Exception as e:
            logger.error(f"Error composing thesis for {token}: {e}")
            # Return minimal thesis on error
            return TradingThesis(
                token=token,
                timestamp=datetime.utcnow().isoformat(),
                window_minutes=window_minutes,
                narrative_heat=0.0,
                consensus=0.0,
                top_event="unknown",
                p_up_60m=0.5,
                confidence="LOW",
                hype_velocity=0.0,
                risk_polarity=0.0,
                reasoning=["Error generating thesis - insufficient data"],
                guardrails=["High uncertainty - avoid trading"],
                evidence=[],
                features_snapshot={}
            )
    
    def _generate_reasoning(
        self,
        token: str,
        bucket_data: Dict[str, Any],
        prediction: PredictionResult,
        narrative_heat: float,
        consensus: float,
        hype_velocity: float
    ) -> List[str]:
        """Generate human-readable reasoning for the thesis"""
        reasoning = []
        
        try:
            top_event = bucket_data.get('top_event') or 'market-note'
            event_dist = bucket_data.get('event_distribution') or {}
            
            # Ensure narrative_heat, consensus, hype_velocity are not None
            narrative_heat = narrative_heat or 0.0
            consensus = consensus or 0.0
            hype_velocity = hype_velocity or 0.0
            
            # Narrative strength analysis
            if abs(narrative_heat) > 2.0:
                if narrative_heat > 0:
                    reasoning.append(f"Strong positive narrative momentum (heat: {narrative_heat:.2f})")
                else:
                    reasoning.append(f"Strong negative narrative pressure (heat: {narrative_heat:.2f})")
            elif abs(narrative_heat) > 1.0:
                reasoning.append(f"Moderate narrative activity detected (heat: {narrative_heat:.2f})")
            else:
                reasoning.append("Low narrative activity - limited market attention")
            
            # Consensus analysis with None safety
            if consensus > 0.7:
                event_prob = event_dist.get(top_event) or 0.0
                reasoning.append(f"High consensus {top_event} narrative ({consensus:.0%} agreement, {event_prob:.0%} probability)")
            elif consensus > 0.5:
                reasoning.append(f"Moderate consensus around {top_event} theme ({consensus:.0%} agreement)")
            else:
                reasoning.append("Mixed narratives - low consensus among sources")
            
            # Hype velocity analysis
            if hype_velocity > 0.2:
                reasoning.append(f"Narrative accelerating rapidly (+{hype_velocity:.0%} vs previous window)")
            elif hype_velocity < -0.2:
                reasoning.append(f"Narrative momentum declining ({hype_velocity:.0%} vs previous window)")
            
            # Event-specific reasoning with None safety
            if top_event == "listing" and (event_dist.get(top_event) or 0) > 0.6:
                reasoning.append("Exchange listing narrative could drive short-term price action")
            elif top_event == "partnership" and (event_dist.get(top_event) or 0) > 0.6:
                reasoning.append("Partnership announcements often create bullish sentiment")
            elif top_event == "hack" and (event_dist.get(top_event) or 0) > 0.4:
                reasoning.append("Security concerns dominating narrative - high risk")
            elif top_event == "regulatory" and (event_dist.get(top_event) or 0) > 0.4:
                reasoning.append("Regulatory uncertainty creating market volatility")
            
            # Liquidity considerations with None safety
            liquidity = bucket_data.get('liquidity_usd') or 0
            if liquidity > 1_000_000:
                reasoning.append(f"Adequate liquidity for trading (est. ${liquidity:,.0f})")
            elif liquidity > 100_000:
                reasoning.append(f"Moderate liquidity - exercise caution (est. ${liquidity:,.0f})")
            else:
                reasoning.append("Low liquidity - high slippage risk")
            
            # Feature importance insights with None safety
            if prediction.feature_importance and len(prediction.feature_importance) > 0:
                try:
                    top_feature = max(prediction.feature_importance, key=prediction.feature_importance.get)
                    reasoning.append(f"Primary signal: {top_feature.replace('_', ' ')} (key driver)")
                except (ValueError, TypeError):
                    # Skip if feature_importance is invalid
                    pass
            
            return reasoning[:6]  # Limit to 6 reasons for readability
            
        except Exception as e:
            logger.error(f"Error generating reasoning: {e}")
            return [f"Analysis generated for {token} token", "Moderate confidence in direction"]
    
    def _generate_guardrails(
        self,
        consensus: float,
        risk_polarity: float,
        narrative_heat: float,
        top_event: str
    ) -> List[str]:
        """Generate risk management guardrails"""
        guardrails = []
        
        try:
            # Ensure parameters are not None
            consensus = consensus or 0.0
            risk_polarity = risk_polarity or 0.0
            narrative_heat = narrative_heat or 0.0
            top_event = top_event or 'market-note'
            
            # Consensus-based guardrails
            if consensus < 0.4:
                guardrails.append("If consensus drops further below 40%, invalidate thesis")
            
            # Risk polarity guardrails
            if risk_polarity < -0.1:
                guardrails.append("If negative events (hack/regulatory) spike, exit immediately")
            
            # Narrative heat guardrails
            if abs(narrative_heat) > 3.0:
                guardrails.append("Extreme narrative heat - consider taking profits at +20%")
            
            # Event-specific guardrails
            if top_event in self.risk_events:
                guardrails.append(f"Monitor {top_event} developments closely - ready to exit")
            
            # Time-based guardrails
            guardrails.append("Re-evaluate thesis if no price movement within 2 hours")
            
            # Volatility guardrails
            guardrails.append("Set stop-loss at -15% to limit downside risk")
            
            # Liquidity guardrails
            guardrails.append("Monitor order book depth - exit if liquidity drops >50%")
            
            return guardrails[:4]  # Limit to 4 guardrails
            
        except Exception as e:
            logger.error(f"Error generating guardrails: {e}")
            return ["Monitor position closely", "Set appropriate stop-losses"]
    
    async def _get_evidence(self, token: str, bucket_ts: Optional[str] = None) -> List[EvidenceItem]:
        """Get evidence articles supporting the thesis"""
        db = SessionLocal()
        try:
            # Get recent articles for the token
            query = db.query(Article).filter(Article.token == token)
            
            if bucket_ts:
                # Get articles from the specific bucket
                target_time = datetime.fromisoformat(bucket_ts.replace('Z', '+00:00'))
                query = query.filter(Article.bucket_ts == target_time)
            else:
                # Get articles from last 24 hours
                since = datetime.utcnow() - timedelta(hours=24)
                query = query.filter(Article.created_at >= since)
            
            # Order by weight and limit results
            articles = query.order_by(Article.final_weight.desc()).limit(10).all()
            
            evidence = []
            for article in articles:
                if not article.title or not article.url:
                    continue
                
                # Determine primary event type with None safety
                event_probs = article.event_probs or {}
                try:
                    top_event = max(event_probs, key=event_probs.get) if event_probs and len(event_probs) > 0 else "unknown"
                except (ValueError, TypeError):
                    top_event = "unknown"
                
                # Create evidence item with None safety
                title = article.title or "Untitled Article"
                if len(title) > 100:
                    title = title[:100] + "..."
                
                evidence_item = EvidenceItem(
                    title=title,
                    url=article.url or "",
                    weight=article.final_weight or 0.0,
                    event_type=top_event,
                    sentiment=article.sentiment_score or 0.0
                )
                
                evidence.append(evidence_item)
            
            # Sort by weight descending
            evidence.sort(key=lambda x: x.weight, reverse=True)
            
            return evidence[:8]  # Return top 8 evidence items
            
        except Exception as e:
            logger.error(f"Error getting evidence: {e}")
            return []
        finally:
            db.close()
    
    def to_dict(self, thesis: TradingThesis) -> Dict[str, Any]:
        """Convert TradingThesis to dictionary for API response"""
        return {
            "token": thesis.token,
            "timestamp": thesis.timestamp,
            "window_minutes": thesis.window_minutes,
            "narrative_heat": thesis.narrative_heat,
            "consensus": thesis.consensus,
            "top_event": thesis.top_event,
            "p_up_60m": thesis.p_up_60m,
            "confidence": thesis.confidence,
            "hype_velocity": thesis.hype_velocity,
            "risk_polarity": thesis.risk_polarity,
            "reasoning": thesis.reasoning,
            "guardrails": thesis.guardrails,
            "evidence": [
                {
                    "title": ev.title,
                    "url": ev.url,
                    "weight": ev.weight,
                    "event_type": ev.event_type,
                    "sentiment": ev.sentiment
                }
                for ev in thesis.evidence
            ],
            "features_snapshot": thesis.features_snapshot
        }
    
    def get_thesis_summary(self, thesis: TradingThesis) -> str:
        """Get a brief text summary of the thesis"""
        try:
            direction = "BULLISH" if thesis.p_up_60m > 0.6 else "BEARISH" if thesis.p_up_60m < 0.4 else "NEUTRAL"
            
            summary = f"{direction} {thesis.token} - {thesis.confidence} confidence ({thesis.p_up_60m:.0%} up probability). "
            summary += f"Primary narrative: {thesis.top_event} with {thesis.consensus:.0%} consensus. "
            
            if thesis.reasoning:
                summary += f"Key factor: {thesis.reasoning[0]}"
            
            return summary
            
        except Exception as e:
            logger.error(f"Error generating thesis summary: {e}")
            return f"{thesis.token} analysis - {thesis.confidence} confidence"