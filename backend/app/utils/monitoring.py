"""
Monitoring and metrics utilities for AgentChain.Trade
Provides structured logging, metrics collection, and alerting
"""

import time
import logging
import json
import asyncio
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from functools import wraps
from contextlib import asynccontextmanager
from dataclasses import dataclass, asdict
import psutil
import os

try:
    from prometheus_client import Counter, Histogram, Gauge, Info, start_http_server, CollectorRegistry
    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False

logger = logging.getLogger(__name__)

@dataclass
class MetricData:
    """Container for metric data"""
    name: str
    value: float
    labels: Dict[str, str] = None
    timestamp: datetime = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now(timezone.utc)
        if self.labels is None:
            self.labels = {}

class StructuredLogger:
    """Enhanced structured logging with context and correlation IDs"""
    
    def __init__(self, name: str):
        self.logger = logging.getLogger(name)
        self.context = {}
        
    def set_context(self, **kwargs):
        """Set logging context for this logger instance"""
        self.context.update(kwargs)
        
    def _format_message(self, level: str, message: str, **kwargs):
        """Format log message with structure and context"""
        log_data = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": level,
            "message": message,
            "service": "ntm-trading-engine",
            "context": self.context,
            **kwargs
        }
        return json.dumps(log_data, default=str)
    
    def debug(self, message: str, **kwargs):
        self.logger.debug(self._format_message("DEBUG", message, **kwargs))
        
    def info(self, message: str, **kwargs):
        self.logger.info(self._format_message("INFO", message, **kwargs))
        
    def warning(self, message: str, **kwargs):
        self.logger.warning(self._format_message("WARNING", message, **kwargs))
        
    def error(self, message: str, error: Exception = None, **kwargs):
        if error:
            kwargs["error_type"] = error.__class__.__name__
            kwargs["error_message"] = str(error)
        self.logger.error(self._format_message("ERROR", message, **kwargs))
        
    def critical(self, message: str, error: Exception = None, **kwargs):
        if error:
            kwargs["error_type"] = error.__class__.__name__
            kwargs["error_message"] = str(error)
        self.logger.critical(self._format_message("CRITICAL", message, **kwargs))

class MetricsCollector:
    """Centralized metrics collection and reporting"""
    
    def __init__(self, enable_prometheus: bool = True):
        self.enable_prometheus = enable_prometheus and PROMETHEUS_AVAILABLE
        self.metrics_data: List[MetricData] = []
        
        if self.enable_prometheus:
            self.registry = CollectorRegistry()
            self._init_prometheus_metrics()
            
    def _init_prometheus_metrics(self):
        """Initialize Prometheus metrics"""
        self.request_count = Counter(
            'ntm_requests_total',
            'Total requests processed',
            ['method', 'endpoint', 'status_code'],
            registry=self.registry
        )
        
        self.request_duration = Histogram(
            'ntm_request_duration_seconds',
            'Request processing duration',
            ['method', 'endpoint'],
            registry=self.registry
        )
        
        self.api_calls = Counter(
            'ntm_external_api_calls_total',
            'External API calls made',
            ['service', 'status'],
            registry=self.registry
        )
        
        self.circuit_breaker_state = Gauge(
            'ntm_circuit_breaker_state',
            'Circuit breaker state (0=closed, 1=half-open, 2=open)',
            ['service'],
            registry=self.registry
        )
        
        self.articles_processed = Counter(
            'ntm_articles_processed_total',
            'Total articles processed',
            ['token', 'status'],
            registry=self.registry
        )
        
        self.predictions_made = Counter(
            'ntm_predictions_made_total',
            'Total predictions made',
            ['token', 'model_type'],
            registry=self.registry
        )
        
        self.narrative_heat = Gauge(
            'ntm_narrative_heat_current',
            'Current narrative heat score',
            ['token'],
            registry=self.registry
        )
        
        self.system_resources = Gauge(
            'ntm_system_resources',
            'System resource usage',
            ['resource_type'],
            registry=self.registry
        )
        
        # Application info
        self.app_info = Info(
            'ntm_application_info',
            'Application information',
            registry=self.registry
        )
        self.app_info.info({
            'version': os.getenv('APP_VERSION', '1.0.0'),
            'environment': os.getenv('ENVIRONMENT', 'development'),
            'python_version': f"{psutil.sys.version_info.major}.{psutil.sys.version_info.minor}.{psutil.sys.version_info.micro}"
        })
    
    def record_request(self, method: str, endpoint: str, status_code: int, duration: float):
        """Record HTTP request metrics"""
        if self.enable_prometheus:
            self.request_count.labels(method=method, endpoint=endpoint, status_code=status_code).inc()
            self.request_duration.labels(method=method, endpoint=endpoint).observe(duration)
        
        self.metrics_data.append(MetricData(
            name="request",
            value=duration,
            labels={
                "method": method,
                "endpoint": endpoint,
                "status_code": str(status_code)
            }
        ))
    
    def record_api_call(self, service: str, success: bool, duration: float = None):
        """Record external API call metrics"""
        status = "success" if success else "failure"
        
        if self.enable_prometheus:
            self.api_calls.labels(service=service, status=status).inc()
        
        labels = {"service": service, "status": status}
        if duration is not None:
            labels["duration"] = str(duration)
            
        self.metrics_data.append(MetricData(
            name="api_call",
            value=1.0,
            labels=labels
        ))
    
    def update_circuit_breaker_state(self, service: str, state: str):
        """Update circuit breaker state"""
        state_mapping = {"closed": 0, "half_open": 1, "open": 2}
        state_value = state_mapping.get(state.lower(), 0)
        
        if self.enable_prometheus:
            self.circuit_breaker_state.labels(service=service).set(state_value)
        
        self.metrics_data.append(MetricData(
            name="circuit_breaker_state",
            value=state_value,
            labels={"service": service, "state": state}
        ))
    
    def record_article_processed(self, token: str, success: bool):
        """Record article processing metrics"""
        status = "success" if success else "failure"
        
        if self.enable_prometheus:
            self.articles_processed.labels(token=token, status=status).inc()
        
        self.metrics_data.append(MetricData(
            name="article_processed",
            value=1.0,
            labels={"token": token, "status": status}
        ))
    
    def record_prediction(self, token: str, model_type: str):
        """Record prediction metrics"""
        if self.enable_prometheus:
            self.predictions_made.labels(token=token, model_type=model_type).inc()
        
        self.metrics_data.append(MetricData(
            name="prediction_made",
            value=1.0,
            labels={"token": token, "model_type": model_type}
        ))
    
    def update_narrative_heat(self, token: str, heat_score: float):
        """Update narrative heat gauge"""
        if self.enable_prometheus:
            self.narrative_heat.labels(token=token).set(heat_score)
        
        self.metrics_data.append(MetricData(
            name="narrative_heat",
            value=heat_score,
            labels={"token": token}
        ))
    
    def update_system_resources(self):
        """Update system resource metrics"""
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        
        if self.enable_prometheus:
            self.system_resources.labels(resource_type='cpu_percent').set(cpu_percent)
            self.system_resources.labels(resource_type='memory_percent').set(memory.percent)
            self.system_resources.labels(resource_type='disk_percent').set(disk.percent)
            self.system_resources.labels(resource_type='memory_available_gb').set(memory.available / (1024**3))
    
    def get_metrics_summary(self) -> Dict[str, Any]:
        """Get summary of collected metrics"""
        if not self.metrics_data:
            return {}
        
        summary = {
            "total_metrics": len(self.metrics_data),
            "latest_timestamp": max(m.timestamp for m in self.metrics_data).isoformat(),
            "metrics_by_type": {}
        }
        
        # Group by metric name
        for metric in self.metrics_data:
            if metric.name not in summary["metrics_by_type"]:
                summary["metrics_by_type"][metric.name] = {"count": 0, "latest_value": 0}
            summary["metrics_by_type"][metric.name]["count"] += 1
            summary["metrics_by_type"][metric.name]["latest_value"] = metric.value
        
        return summary
    
    def clear_metrics(self):
        """Clear collected metrics data"""
        self.metrics_data.clear()

class PerformanceMonitor:
    """Performance monitoring and profiling utilities"""
    
    def __init__(self, metrics_collector: MetricsCollector):
        self.metrics = metrics_collector
        self.active_requests = {}
        
    @asynccontextmanager
    async def track_request(self, method: str, endpoint: str):
        """Context manager for tracking request performance"""
        start_time = time.time()
        request_id = f"{method}:{endpoint}:{start_time}"
        
        self.active_requests[request_id] = {
            "method": method,
            "endpoint": endpoint,
            "start_time": start_time
        }
        
        try:
            yield
            status_code = 200
        except Exception as e:
            status_code = 500
            logger.error(f"Request failed: {method} {endpoint}", error=e)
            raise
        finally:
            duration = time.time() - start_time
            self.metrics.record_request(method, endpoint, status_code, duration)
            self.active_requests.pop(request_id, None)
    
    def track_api_call(self, service: str):
        """Decorator for tracking external API calls"""
        def decorator(func):
            @wraps(func)
            async def async_wrapper(*args, **kwargs):
                start_time = time.time()
                try:
                    result = await func(*args, **kwargs)
                    success = True
                    return result
                except Exception as e:
                    success = False
                    raise
                finally:
                    duration = time.time() - start_time
                    self.metrics.record_api_call(service, success, duration)
            
            @wraps(func)
            def sync_wrapper(*args, **kwargs):
                start_time = time.time()
                try:
                    result = func(*args, **kwargs)
                    success = True
                    return result
                except Exception as e:
                    success = False
                    raise
                finally:
                    duration = time.time() - start_time
                    self.metrics.record_api_call(service, success, duration)
            
            return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper
        return decorator
    
    def get_active_requests(self) -> Dict[str, Any]:
        """Get information about currently active requests"""
        current_time = time.time()
        active = {}
        
        for request_id, info in self.active_requests.items():
            active[request_id] = {
                **info,
                "duration_so_far": current_time - info["start_time"]
            }
        
        return active

class AlertManager:
    """Alert management and notification system"""
    
    def __init__(self, metrics_collector: MetricsCollector):
        self.metrics = metrics_collector
        self.alert_rules = []
        self.active_alerts = {}
        
    def add_rule(self, name: str, condition_func, severity: str = "warning", cooldown: int = 300):
        """Add an alert rule"""
        self.alert_rules.append({
            "name": name,
            "condition": condition_func,
            "severity": severity,
            "cooldown": cooldown,
            "last_fired": 0
        })
    
    async def check_alerts(self):
        """Check all alert rules and fire alerts if needed"""
        current_time = time.time()
        
        for rule in self.alert_rules:
            # Skip if in cooldown period
            if current_time - rule["last_fired"] < rule["cooldown"]:
                continue
            
            try:
                if await rule["condition"](self.metrics):
                    await self._fire_alert(rule, current_time)
            except Exception as e:
                logger.error(f"Error checking alert rule {rule['name']}", error=e)
    
    async def _fire_alert(self, rule: Dict, timestamp: float):
        """Fire an alert"""
        alert_data = {
            "name": rule["name"],
            "severity": rule["severity"],
            "timestamp": timestamp,
            "message": f"Alert: {rule['name']} triggered"
        }
        
        self.active_alerts[rule["name"]] = alert_data
        rule["last_fired"] = timestamp
        
        logger.warning(f"ALERT FIRED: {rule['name']}", alert=alert_data)
        
        # Here you could add integrations with:
        # - Slack/Discord webhooks
        # - PagerDuty
        # - Email notifications
        # - etc.
    
    def get_active_alerts(self) -> Dict[str, Any]:
        """Get currently active alerts"""
        return self.active_alerts.copy()

# Global instances
structured_logger = StructuredLogger("ntm-trading")
metrics_collector = MetricsCollector(enable_prometheus=os.getenv("ENABLE_METRICS", "false").lower() == "true")
performance_monitor = PerformanceMonitor(metrics_collector)
alert_manager = AlertManager(metrics_collector)

# Setup default alert rules
async def high_error_rate_condition(metrics: MetricsCollector):
    """Alert if error rate is too high"""
    summary = metrics.get_metrics_summary()
    error_count = 0
    total_count = 0
    
    for metric in metrics.metrics_data:
        if metric.name == "request" and "status_code" in metric.labels:
            total_count += 1
            if metric.labels["status_code"].startswith("5"):
                error_count += 1
    
    if total_count > 10:  # Only check if we have enough data
        error_rate = error_count / total_count
        return error_rate > 0.1  # Alert if > 10% error rate
    
    return False

async def circuit_breaker_open_condition(metrics: MetricsCollector):
    """Alert if any circuit breaker is open"""
    for metric in metrics.metrics_data:
        if metric.name == "circuit_breaker_state" and metric.value == 2:  # Open state
            return True
    return False

async def high_response_time_condition(metrics: MetricsCollector):
    """Alert if response times are too high"""
    recent_requests = [m for m in metrics.metrics_data if m.name == "request"][-20:]  # Last 20 requests
    if len(recent_requests) >= 10:
        avg_duration = sum(r.value for r in recent_requests) / len(recent_requests)
        return avg_duration > 5.0  # Alert if avg response time > 5 seconds
    return False

# Add default alert rules
alert_manager.add_rule("high_error_rate", high_error_rate_condition, "critical", cooldown=600)
alert_manager.add_rule("circuit_breaker_open", circuit_breaker_open_condition, "warning", cooldown=300)
alert_manager.add_rule("high_response_time", high_response_time_condition, "warning", cooldown=300)

def setup_monitoring(app):
    """Setup monitoring for FastAPI application"""
    @app.middleware("http")
    async def monitoring_middleware(request, call_next):
        method = request.method
        endpoint = str(request.url.path)
        
        async with performance_monitor.track_request(method, endpoint):
            response = await call_next(request)
            return response
    
    # Start background tasks
    @app.on_event("startup")
    async def start_monitoring():
        if metrics_collector.enable_prometheus:
            # Start Prometheus metrics server
            metrics_port = int(os.getenv("METRICS_PORT", 9000))
            start_http_server(metrics_port, registry=metrics_collector.registry)
            logger.info(f"Prometheus metrics server started on port {metrics_port}")
        
        # Start alert checking task
        asyncio.create_task(periodic_alert_check())
        
        # Start system resource monitoring
        asyncio.create_task(periodic_resource_monitoring())
    
    return app

async def periodic_alert_check():
    """Periodic task to check alerts"""
    while True:
        try:
            await alert_manager.check_alerts()
            await asyncio.sleep(60)  # Check every minute
        except Exception as e:
            logger.error("Error in periodic alert check", error=e)
            await asyncio.sleep(60)

async def periodic_resource_monitoring():
    """Periodic task to update system resource metrics"""
    while True:
        try:
            metrics_collector.update_system_resources()
            await asyncio.sleep(30)  # Update every 30 seconds
        except Exception as e:
            logger.error("Error in resource monitoring", error=e)
            await asyncio.sleep(30)