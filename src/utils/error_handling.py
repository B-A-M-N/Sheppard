"""
Error handling utilities for Sheppard V3.

Provides:
- Circuit breaker pattern for degraded dependency handling
- Connection health monitoring for database triad
- Structured error logging
- Graceful degradation strategies
"""
import asyncio
import logging
import time
from typing import Callable, Any, Optional
from enum import Enum
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing, rejecting calls
    HALF_OPEN = "half_open"  # Testing if recovered


@dataclass
class CircuitBreakerConfig:
    failure_threshold: int = 5  # Failures before opening
    recovery_timeout: float = 30.0  # Seconds before trying again
    success_threshold: int = 2  # Successes needed to close from half-open


class CircuitBreakerError(Exception):
    """Raised when circuit breaker is open."""
    pass


class CircuitBreaker:
    """
    Circuit breaker pattern for resilient service communication.
    
    States:
    - CLOSED: Normal operation, requests pass through
    - OPEN: Failing, requests immediately rejected
    - HALF_OPEN: Testing recovery, limited requests allowed
    """
    
    def __init__(self, name: str, config: CircuitBreakerConfig = CircuitBreakerConfig()):
        self.name = name
        self.config = config
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time = 0
        self._lock = asyncio.Lock()
    
    async def call(self, func: Callable, *args, **kwargs) -> Any:
        """Execute function through circuit breaker."""
        async with self._lock:
            if self.state == CircuitState.OPEN:
                if time.time() - self.last_failure_time < self.config.recovery_timeout:
                    logger.warning(f"[CircuitBreaker:{self.name}] OPEN - rejecting call to {func.__name__}")
                    raise CircuitBreakerError(f"Circuit breaker {self.name} is OPEN")
                else:
                    logger.info(f"[CircuitBreaker:{self.name}] Transitioning to HALF_OPEN")
                    self.state = CircuitState.HALF_OPEN
                    self.success_count = 0
        
        try:
            result = await func(*args, **kwargs) if asyncio.iscoroutinefunction(func) else func(*args, **kwargs)
            
            async with self._lock:
                self._on_success()
            
            return result
        except Exception as e:
            async with self._lock:
                self._on_failure(e)
            raise
    
    def _on_success(self):
        """Handle successful call."""
        if self.state == CircuitState.HALF_OPEN:
            self.success_count += 1
            if self.success_count >= self.config.success_threshold:
                logger.info(f"[CircuitBreaker:{self.name}] Transitioning to CLOSED (recovered)")
                self.state = CircuitState.CLOSED
                self.failure_count = 0
                self.success_count = 0
        else:
            self.failure_count = 0
    
    def _on_failure(self, error: Exception):
        """Handle failed call."""
        self.failure_count += 1
        self.last_failure_time = time.time()
        
        if self.state == CircuitState.HALF_OPEN:
            logger.warning(f"[CircuitBreaker:{self.name}] HALF_OPEN failed, returning to OPEN")
            self.state = CircuitState.OPEN
        elif self.failure_count >= self.config.failure_threshold:
            logger.error(f"[CircuitBreaker:{self.name}] OPENING after {self.failure_count} failures")
            self.state = CircuitState.OPEN
    
    @property
    def is_healthy(self) -> bool:
        return self.state != CircuitState.OPEN


@dataclass
class HealthCheckResult:
    component: str
    healthy: bool
    latency_ms: float = 0.0
    error: Optional[str] = None


class ConnectionHealthMonitor:
    """
    Monitors health of database triad (Postgres, Redis, Chroma).
    
    Provides:
    - Periodic health checks
    - Circuit breaker integration
    - Graceful degradation signals
    """
    
    def __init__(self, adapter=None):
        self.adapter = adapter
        self.circuit_breakers = {
            'postgres': CircuitBreaker('postgres', CircuitBreakerConfig(failure_threshold=3, recovery_timeout=10)),
            'redis': CircuitBreaker('redis', CircuitBreakerConfig(failure_threshold=5, recovery_timeout=5)),
            'chroma': CircuitBreaker('chroma', CircuitBreakerConfig(failure_threshold=5, recovery_timeout=5)),
        }
        self._health_cache = {}
        self._cache_ttl = 5  # seconds
    
    async def check_postgres(self) -> HealthCheckResult:
        """Check Postgres connectivity."""
        try:
            start = time.time()
            if self.adapter and self.adapter.pg:
                await self.circuit_breakers['postgres'].call(
                    self.adapter.pg.pool.fetchval,
                    "SELECT 1"
                )
            latency = (time.time() - start) * 1000
            return HealthCheckResult('postgres', healthy=True, latency_ms=latency)
        except Exception as e:
            logger.error(f"[HealthCheck] Postgres unhealthy: {e}")
            return HealthCheckResult('postgres', healthy=False, error=str(e))
    
    async def check_redis(self) -> HealthCheckResult:
        """Check Redis connectivity."""
        try:
            start = time.time()
            if self.adapter and self.adapter.redis_runtime:
                await self.circuit_breakers['redis'].call(
                    self.adapter.redis_runtime.ping
                )
            latency = (time.time() - start) * 1000
            return HealthCheckResult('redis', healthy=True, latency_ms=latency)
        except Exception as e:
            logger.error(f"[HealthCheck] Redis unhealthy: {e}")
            return HealthCheckResult('redis', healthy=False, error=str(e))
    
    async def check_chroma(self) -> HealthCheckResult:
        """Check Chroma connectivity."""
        try:
            start = time.time()
            if self.adapter and self.adapter.chroma:
                await self.circuit_breakers['chroma'].call(
                    self._check_chroma_sync
                )
            latency = (time.time() - start) * 1000
            return HealthCheckResult('chroma', healthy=True, latency_ms=latency)
        except Exception as e:
            logger.error(f"[HealthCheck] Chroma unhealthy: {e}")
            return HealthCheckResult('chroma', healthy=False, error=str(e))
    
    def _check_chroma_sync(self):
        """Synchronous Chroma health check."""
        if self.adapter.chroma.client:
            self.adapter.chroma.client.heartbeat()
    
    async def check_all(self) -> dict[str, HealthCheckResult]:
        """Run all health checks concurrently."""
        results = await asyncio.gather(
            self.check_postgres(),
            self.check_redis(),
            self.check_chroma(),
            return_exceptions=True
        )
        
        health_dict = {}
        for result in results:
            if isinstance(result, Exception):
                health_dict['unknown'] = HealthCheckResult('unknown', healthy=False, error=str(result))
            else:
                health_dict[result.component] = result
        
        return health_dict
    
    def is_degraded(self) -> bool:
        """Check if system is in degraded state."""
        return not all(cb.is_healthy for cb in self.circuit_breakers.values())
    
    def get_circuit_breaker(self, component: str) -> CircuitBreaker:
        """Get circuit breaker for component."""
        return self.circuit_breakers.get(component)


class StructuredError(Exception):
    """
    Structured error with context for better debugging.
    
    Usage:
        raise StructuredError(
            operation="scrape",
            url=url,
            error="Connection refused",
            mission_id=mission_id
        )
    """
    
    def __init__(self, operation: str, error: str, **context):
        self.operation = operation
        self.error = error
        self.context = context
        super().__init__(f"[{operation}] {error}")
    
    def to_dict(self) -> dict:
        return {
            'operation': self.operation,
            'error': self.error,
            **self.context
        }


async def safe_execute(func: Callable, fallback: Any = None, **context) -> Any:
    """
    Execute function with error handling and optional fallback.
    
    Usage:
        result = await safe_execute(
            scraper.scrape,
            fallback={"content": "", "status": "degraded"},
            url=url
        )
    """
    try:
        return await func() if asyncio.iscoroutinefunction(func) else func()
    except Exception as e:
        logger.error(f"[SafeExecute] Failed: {e}", extra=context)
        return fallback
