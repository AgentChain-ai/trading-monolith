import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
import lightgbm as lgb
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, roc_auc_score
import joblib
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
import json
from pathlib import Path
from dataclasses import dataclass
from sqlalchemy.orm import Session

from ..models import Article, Bucket, Label, MLModel
from ..database import SessionLocal

logger = logging.getLogger(__name__)

@dataclass
class PredictionResult:
    """Container for ML prediction results"""
    probability_up: float
    confidence: str
    feature_importance: Dict[str, float]
    features_used: Dict[str, float]

@dataclass
class ModelPerformance:
    """Container for model performance metrics"""
    accuracy: float
    precision: float
    recall: float
    f1_score: float
    roc_auc: float

class MLEngine:
    """Machine Learning engine for trading signal prediction"""
    
    # Feature names for the ML model
    FEATURE_NAMES = [
        'narrative_heat',
        'positive_heat', 
        'negative_heat',
        'hype_velocity',
        'consensus',
        'risk_polarity',
        # Event probabilities
        'p_listing', 'p_partnership', 'p_hack', 'p_regulatory',
        'p_funding', 'p_tech', 'p_market_note', 'p_depeg', 'p_op_ed',
        # Optional on-chain features
        'liquidity_usd_log', 'trades_count_change', 'spread_estimate'
    ]
    
    def __init__(self, models_dir: str = "models/"):
        self.models_dir = Path(models_dir)
        self.models_dir.mkdir(exist_ok=True)
        
        # Model configurations
        self.model_configs = {
            'logistic': {
                'class': LogisticRegression,
                'params': {
                    'random_state': 42,
                    'max_iter': 1000,
                    'class_weight': 'balanced'
                }
            },
            'random_forest': {
                'class': RandomForestClassifier,
                'params': {
                    'n_estimators': 100,
                    'random_state': 42,
                    'class_weight': 'balanced',
                    'max_depth': 10
                }
            },
            'lightgbm': {
                'class': lgb.LGBMClassifier,
                'params': {
                    'random_state': 42,
                    'class_weight': 'balanced',
                    'verbosity': -1,
                    'num_leaves': 31,
                    'learning_rate': 0.1
                }
            }
        }
        
        self.current_model = None
        self.current_scaler = None
        self.current_model_version = None
        
    def prepare_features(self, bucket_data: Dict[str, Any]) -> np.ndarray:
        """
        Prepare feature vector from bucket data with None safety
        
        Args:
            bucket_data: Dictionary containing bucket features
            
        Returns:
            Feature vector as numpy array
        """
        try:
            features = []
            
            # Core narrative features with None safety
            features.append(bucket_data.get('narrative_heat') or 0.0)
            features.append(bucket_data.get('positive_heat') or 0.0)
            features.append(bucket_data.get('negative_heat') or 0.0)
            features.append(bucket_data.get('hype_velocity') or 0.0)
            features.append(bucket_data.get('consensus') or 0.0)
            features.append(bucket_data.get('risk_polarity') or 0.0)
            
            # Event distribution probabilities with None safety
            event_dist = bucket_data.get('event_distribution') or {}
            features.append(event_dist.get('listing') or 0.0)
            features.append(event_dist.get('partnership') or 0.0)
            features.append(event_dist.get('hack') or 0.0)
            features.append(event_dist.get('regulatory') or 0.0)
            features.append(event_dist.get('funding') or 0.0)
            features.append(event_dist.get('tech') or 0.0)
            features.append(event_dist.get('market-note') or 0.0)
            features.append(event_dist.get('depeg') or 0.0)
            features.append(event_dist.get('op-ed') or 0.0)
            
            # On-chain features with None safety
            liquidity = bucket_data.get('liquidity_usd') or 1.0
            features.append(np.log1p(max(liquidity, 1.0)))  # Log transform
            features.append(bucket_data.get('trades_count_change') or 0.0)
            features.append(bucket_data.get('spread_estimate') or 0.0)
            
            # Ensure all features are numeric and not None
            safe_features = []
            for feature in features:
                if feature is None or not isinstance(feature, (int, float)):
                    safe_features.append(0.0)
                else:
                    safe_features.append(float(feature))
            
            return np.array(safe_features).reshape(1, -1)
            
        except Exception as e:
            logger.error(f"Error preparing features: {e}")
            return np.zeros((1, len(self.FEATURE_NAMES)))
    
    async def predict(self, bucket_data: Dict[str, Any]) -> PredictionResult:
        """
        Make trading prediction for a token bucket
        
        Args:
            bucket_data: Bucket data with features
            
        Returns:
            PredictionResult with probability and explanation
        """
        try:
            # Load model if not already loaded
            if self.current_model is None:
                await self._load_latest_model()
            
            # If still no model, attempt automatic training
            if self.current_model is None:
                logger.info("No trained model found - attempting automatic training")
                model_version = await self._auto_train_model()
                
                if model_version:
                    logger.info(f"Successfully auto-trained model: {model_version}")
                else:
                    logger.warning("Auto-training failed, using intelligent default prediction")
                    return self._get_intelligent_default_prediction(bucket_data)
            
            # Prepare features
            X = self.prepare_features(bucket_data)
            
            # Scale features if scaler is available
            if self.current_scaler is not None:
                X = self.current_scaler.transform(X)
            
            # Make prediction
            prob_up = self.current_model.predict_proba(X)[0][1]
            
            # Determine confidence level
            confidence = self._determine_confidence(prob_up, bucket_data)
            
            # Get feature importance
            feature_importance = self._get_feature_importance(X[0])
            
            # Create features used dictionary
            features_used = dict(zip(self.FEATURE_NAMES, X[0]))
            
            return PredictionResult(
                probability_up=float(prob_up),
                confidence=confidence,
                feature_importance=feature_importance,
                features_used=features_used
            )
            
        except Exception as e:
            logger.error(f"Error in prediction: {e}")
            return PredictionResult(
                probability_up=0.5,
                confidence="LOW",
                feature_importance={},
                features_used={}
            )
    
    async def train_model(self, model_type: str = "lightgbm", min_samples: int = 50) -> Optional[str]:
        """
        Train a new ML model using available data
        
        Args:
            model_type: Type of model to train
            min_samples: Minimum number of samples required for training
            
        Returns:
            Model version string if successful, None otherwise
        """
        try:
            # Load training data
            X, y = await self._load_training_data()
            
            if len(X) < min_samples:
                logger.warning(f"Not enough training samples: {len(X)} < {min_samples}")
                return None
            
            logger.info(f"Training {model_type} model with {len(X)} samples")
            
            # Split data
            X_train, X_test, y_train, y_test = train_test_split(
                X, y, test_size=0.2, random_state=42, stratify=y
            )
            
            # Scale features
            scaler = StandardScaler()
            X_train_scaled = scaler.fit_transform(X_train)
            X_test_scaled = scaler.transform(X_test)
            
            # Train model
            model_config = self.model_configs[model_type]
            model = model_config['class'](**model_config['params'])
            model.fit(X_train_scaled, y_train)
            
            # Evaluate model
            y_pred = model.predict(X_test_scaled)
            y_prob = model.predict_proba(X_test_scaled)[:, 1]
            
            performance = ModelPerformance(
                accuracy=accuracy_score(y_test, y_pred),
                precision=precision_score(y_test, y_pred, zero_division=0),
                recall=recall_score(y_test, y_pred, zero_division=0),
                f1_score=f1_score(y_test, y_pred, zero_division=0),
                roc_auc=roc_auc_score(y_test, y_prob) if len(np.unique(y_test)) > 1 else 0.5
            )
            
            logger.info(f"Model performance - Accuracy: {performance.accuracy:.3f}, "
                       f"F1: {performance.f1_score:.3f}, ROC-AUC: {performance.roc_auc:.3f}")
            
            # Save model
            model_version = f"{model_type}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            model_path = self.models_dir / f"{model_version}.joblib"
            scaler_path = self.models_dir / f"{model_version}_scaler.joblib"
            
            joblib.dump(model, model_path)
            joblib.dump(scaler, scaler_path)
            
            # Save model metadata to database
            await self._save_model_metadata(model_version, model_type, performance)
            
            # Update current model
            self.current_model = model
            self.current_scaler = scaler
            self.current_model_version = model_version
            
            logger.info(f"Model {model_version} trained and saved successfully")
            return model_version
            
        except Exception as e:
            logger.error(f"Error training model: {e}")
            return None
    
    async def _load_training_data(self) -> Tuple[np.ndarray, np.ndarray]:
        """Load training data from database"""
        db = SessionLocal()
        try:
            # Query buckets with labels
            query = db.query(Bucket, Label).join(
                Label, 
                (Bucket.token == Label.token) & (Bucket.bucket_ts == Label.bucket_ts)
            ).filter(Label.label_binary.isnot(None))
            
            results = query.all()
            
            if not results:
                logger.warning("No labeled training data found")
                return np.array([]), np.array([])
            
            X_list = []
            y_list = []
            
            for bucket, label in results:
                # Prepare features from bucket
                bucket_dict = bucket.to_dict()
                features = self.prepare_features(bucket_dict)[0]
                
                X_list.append(features)
                y_list.append(label.label_binary)
            
            X = np.array(X_list)
            y = np.array(y_list)
            
            logger.info(f"Loaded {len(X)} training samples")
            return X, y
            
        finally:
            db.close()
    
    async def _load_latest_model(self) -> bool:
        """Load the latest trained model"""
        try:
            db = SessionLocal()
            try:
                # Get latest active model
                latest_model = db.query(MLModel).filter(
                    MLModel.is_active == True
                ).order_by(MLModel.updated_at.desc()).first()
                
                if not latest_model:
                    logger.warning("No active model found in database")
                    return False
                
                model_path = self.models_dir / f"{latest_model.version}.joblib"
                scaler_path = self.models_dir / f"{latest_model.version}_scaler.joblib"
                
                if not model_path.exists():
                    logger.error(f"Model file not found: {model_path}")
                    return False
                
                # Load model and scaler
                self.current_model = joblib.load(model_path)
                
                if scaler_path.exists():
                    self.current_scaler = joblib.load(scaler_path)
                
                self.current_model_version = latest_model.version
                
                logger.info(f"Loaded model: {latest_model.version}")
                return True
                
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"Error loading model: {e}")
            return False
    
    async def _save_model_metadata(self, version: str, model_type: str, performance: ModelPerformance):
        """Save model metadata to database"""
        db = SessionLocal()
        try:
            # Deactivate previous models
            db.query(MLModel).update({'is_active': False})
            
            # Create new model record
            new_model = MLModel(
                version=version,
                model_type=model_type,
                parameters=self.model_configs[model_type]['params'],
                feature_names=self.FEATURE_NAMES,
                performance_metrics={
                    'accuracy': performance.accuracy,
                    'precision': performance.precision,
                    'recall': performance.recall,
                    'f1_score': performance.f1_score,
                    'roc_auc': performance.roc_auc
                },
                is_active=True
            )
            
            db.add(new_model)
            db.commit()
            
        except Exception as e:
            logger.error(f"Error saving model metadata: {e}")
            db.rollback()
        finally:
            db.close()
    
    def _determine_confidence(self, probability: float, bucket_data: Dict[str, Any]) -> str:
        """Determine confidence level based on probability and other factors"""
        # Base confidence on probability distance from 0.5
        prob_confidence = abs(probability - 0.5) * 2
        
        # Adjust based on consensus and narrative heat
        consensus = bucket_data.get('consensus', 0.0)
        narrative_heat = bucket_data.get('narrative_heat', 0.0)
        
        # Higher consensus and heat increase confidence
        consensus_boost = consensus * 0.2
        heat_boost = min(abs(narrative_heat) / 5.0, 0.3)
        
        final_confidence = prob_confidence + consensus_boost + heat_boost
        
        if final_confidence > 0.7:
            return "HIGH"
        elif final_confidence > 0.4:
            return "MEDIUM"
        else:
            return "LOW"
    
    def _get_feature_importance(self, features: np.ndarray) -> Dict[str, float]:
        """Get feature importance for the current prediction"""
        try:
            if self.current_model is None:
                return {}
            
            # Get feature importance from model
            if hasattr(self.current_model, 'feature_importances_'):
                importances = self.current_model.feature_importances_
            elif hasattr(self.current_model, 'coef_'):
                importances = np.abs(self.current_model.coef_[0])
            else:
                return {}
            
            # Combine with feature values for interpretation
            feature_impact = importances * np.abs(features)
            
            # Normalize to get relative importance
            total_impact = np.sum(feature_impact)
            if total_impact > 0:
                relative_importance = feature_impact / total_impact
            else:
                relative_importance = feature_impact
            
            # Return top features
            importance_dict = dict(zip(self.FEATURE_NAMES, relative_importance))
            
            # Sort by importance and return top 5
            sorted_importance = sorted(
                importance_dict.items(), 
                key=lambda x: x[1], 
                reverse=True
            )
            
            return dict(sorted_importance[:5])
            
        except Exception as e:
            logger.error(f"Error getting feature importance: {e}")
            return {}
    
    async def _auto_train_model(self) -> Optional[str]:
        """Automatically train a model when none exists"""
        try:
            logger.info("Starting automatic model training...")
            
            # Check for existing labeled data
            X, y = await self._load_training_data()
            
            # If insufficient data, generate synthetic training data
            if len(X) < 10:  # Very low threshold for bootstrap
                logger.info(f"Found only {len(X)} labeled samples, generating synthetic data")
                X_synthetic, y_synthetic = await self._generate_synthetic_training_data()
                
                if len(X_synthetic) > 0:
                    # Combine real and synthetic data
                    if len(X) > 0:
                        X = np.vstack([X, X_synthetic])
                        y = np.concatenate([y, y_synthetic])
                    else:
                        X, y = X_synthetic, y_synthetic
                    logger.info(f"Combined dataset now has {len(X)} samples")
                else:
                    logger.error("Failed to generate synthetic training data")
                    return None
            
            # Train with relaxed requirements
            return await self.train_model(model_type="lightgbm", min_samples=max(10, len(X)))
            
        except Exception as e:
            logger.error(f"Error in auto-training: {e}")
            return None
    
    async def _generate_synthetic_training_data(self) -> Tuple[np.ndarray, np.ndarray]:
        """Generate synthetic training data based on existing bucket patterns"""
        try:
            db = SessionLocal()
            try:
                # Get recent buckets without labels to create synthetic data
                recent_buckets = db.query(Bucket).filter(
                    Bucket.created_at >= datetime.utcnow() - timedelta(days=30)
                ).order_by(Bucket.created_at.desc()).limit(50).all()
                
                if not recent_buckets:
                    logger.warning("No recent buckets found for synthetic data generation")
                    return np.array([]), np.array([])
                
                X_synthetic = []
                y_synthetic = []
                
                for bucket in recent_buckets:
                    try:
                        # Extract features
                        bucket_dict = bucket.to_dict()
                        features = self.prepare_features(bucket_dict)[0]
                        
                        # Generate synthetic label based on heuristic rules
                        label = self._generate_synthetic_label(bucket_dict)
                        
                        X_synthetic.append(features)
                        y_synthetic.append(label)
                        
                    except Exception as bucket_error:
                        logger.warning(f"Error processing bucket {bucket.id}: {bucket_error}")
                        continue
                
                if len(X_synthetic) > 0:
                    logger.info(f"Generated {len(X_synthetic)} synthetic training samples")
                    return np.array(X_synthetic), np.array(y_synthetic)
                else:
                    return np.array([]), np.array([])
                    
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"Error generating synthetic data: {e}")
            return np.array([]), np.array([])
    
    def _generate_synthetic_label(self, bucket_data: Dict[str, Any]) -> int:
        """Generate synthetic label using heuristic rules"""
        # Extract key metrics
        narrative_heat = bucket_data.get('narrative_heat', 0.0) or 0.0
        consensus = bucket_data.get('consensus', 0.0) or 0.0
        risk_polarity = bucket_data.get('risk_polarity', 0.0) or 0.0
        hype_velocity = bucket_data.get('hype_velocity', 0.0) or 0.0
        
        # Event distribution analysis
        event_dist = bucket_data.get('event_distribution', {}) or {}
        positive_events = event_dist.get('listing', 0) + event_dist.get('partnership', 0) + event_dist.get('funding', 0)
        negative_events = event_dist.get('hack', 0) + event_dist.get('depeg', 0)
        
        # Heuristic scoring
        score = 0
        
        # Positive indicators
        if narrative_heat > 1.0:
            score += 1
        if consensus > 0.6:
            score += 1
        if hype_velocity > 0.1:
            score += 1
        if positive_events > 0.5:
            score += 2
        if risk_polarity > 0:
            score += 1
        
        # Negative indicators
        if narrative_heat < -1.0:
            score -= 1
        if risk_polarity < -0.1:
            score -= 2
        if negative_events > 0.3:
            score -= 2
        
        # Return binary label (1 for positive prediction, 0 for negative)
        return 1 if score > 0 else 0
    
    def _get_intelligent_default_prediction(self, bucket_data: Dict[str, Any]) -> PredictionResult:
        """Get an intelligent default prediction when no model is available"""
        try:
            # Extract key metrics with safety
            narrative_heat = bucket_data.get('narrative_heat') or 0.0
            consensus = bucket_data.get('consensus') or 0.0
            risk_polarity = bucket_data.get('risk_polarity') or 0.0
            hype_velocity = bucket_data.get('hype_velocity') or 0.0
            
            # Calculate probability based on heuristics
            base_prob = 0.5
            
            # Adjust based on narrative heat
            if abs(narrative_heat) > 0:
                heat_adjustment = min(abs(narrative_heat) * 0.1, 0.2)
                if narrative_heat > 0:
                    base_prob += heat_adjustment
                else:
                    base_prob -= heat_adjustment
            
            # Adjust based on consensus
            if consensus > 0.5:
                base_prob += (consensus - 0.5) * 0.2
            
            # Adjust based on risk polarity
            if risk_polarity != 0:
                base_prob += risk_polarity * 0.15
            
            # Adjust based on hype velocity
            if hype_velocity > 0:
                base_prob += min(hype_velocity * 0.1, 0.1)
            elif hype_velocity < 0:
                base_prob += max(hype_velocity * 0.1, -0.1)
            
            # Clamp probability between 0.1 and 0.9
            probability_up = max(0.1, min(0.9, base_prob))
            
            # Determine confidence based on signal strength
            signal_strength = abs(probability_up - 0.5)
            if signal_strength > 0.3:
                confidence = "HIGH"
            elif signal_strength > 0.15:
                confidence = "MEDIUM"
            else:
                confidence = "LOW"
            
            # Create basic feature importance
            feature_importance = {
                "narrative_heat": abs(narrative_heat) * 0.3,
                "consensus": consensus * 0.25,
                "risk_polarity": abs(risk_polarity) * 0.2,
                "hype_velocity": abs(hype_velocity) * 0.15,
                "overall_signal": signal_strength * 0.1
            }
            
            # Normalize feature importance
            total_importance = sum(feature_importance.values())
            if total_importance > 0:
                feature_importance = {k: v/total_importance for k, v in feature_importance.items()}
            
            logger.info(f"Using intelligent default: prob={probability_up:.3f}, confidence={confidence}")
            
            return PredictionResult(
                probability_up=probability_up,
                confidence=confidence,
                feature_importance=feature_importance,
                features_used={
                    "narrative_heat": narrative_heat,
                    "consensus": consensus,
                    "risk_polarity": risk_polarity,
                    "hype_velocity": hype_velocity
                }
            )
            
        except Exception as e:
            logger.error(f"Error in intelligent default prediction: {e}")
            return PredictionResult(
                probability_up=0.5,
                confidence="LOW",
                feature_importance={},
                features_used={}
            )
    
    async def check_and_retrain_model(self) -> bool:
        """Check if model needs retraining and do it automatically"""
        try:
            db = SessionLocal()
            try:
                # Get current active model
                current_model = db.query(MLModel).filter(MLModel.is_active == True).first()
                
                # Check if we need retraining
                should_retrain = False
                
                if not current_model:
                    logger.info("No active model found - triggering training")
                    should_retrain = True
                else:
                    # Check model age (retrain if older than 7 days)
                    model_age = datetime.utcnow() - current_model.updated_at
                    if model_age.days > 7:
                        logger.info(f"Model is {model_age.days} days old - triggering retraining")
                        should_retrain = True
                    
                    # Check for new labeled data
                    new_labels_count = db.query(Label).filter(
                        Label.created_at > current_model.updated_at
                    ).count()
                    
                    if new_labels_count >= 10:  # Retrain if 10+ new labels
                        logger.info(f"Found {new_labels_count} new labels - triggering retraining")
                        should_retrain = True
                
                if should_retrain:
                    logger.info("Starting automatic model retraining...")
                    new_model_version = await self._auto_train_model()
                    if new_model_version:
                        logger.info(f"Successfully retrained model: {new_model_version}")
                        return True
                    else:
                        logger.error("Automatic retraining failed")
                        return False
                
                return True  # No retraining needed
                
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"Error in check_and_retrain_model: {e}")
            return False
    
    async def get_model_status(self) -> Dict[str, Any]:
        """Get comprehensive model status information"""
        try:
            db = SessionLocal()
            try:
                # Get current model info
                current_model = db.query(MLModel).filter(MLModel.is_active == True).first()
                
                # Count available training data
                labeled_count = db.query(Label).count()
                bucket_count = db.query(Bucket).count()
                
                # Get recent performance if model exists
                performance = None
                if current_model:
                    performance = current_model.performance_metrics
                
                status = {
                    "has_active_model": current_model is not None,
                    "model_version": current_model.version if current_model else None,
                    "model_type": current_model.model_type if current_model else None,
                    "model_age_days": (datetime.utcnow() - current_model.updated_at).days if current_model else None,
                    "labeled_samples": labeled_count,
                    "total_buckets": bucket_count,
                    "performance_metrics": performance,
                    "needs_training": current_model is None or labeled_count == 0,
                    "can_auto_train": bucket_count >= 10 or labeled_count >= 5,
                    "last_updated": current_model.updated_at.isoformat() if current_model else None
                }
                
                return status
                
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"Error getting model status: {e}")
            return {"error": str(e), "has_active_model": False}