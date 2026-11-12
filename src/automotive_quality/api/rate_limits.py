import hashlib
import logging
import math
import threading
from collections.abc import Generator
from dataclasses import dataclass
from enum import StrEnum
from functools import lru_cache
from typing import Annotated
from uuid import uuid4

from fastapi import Depends, HTTPException, status
from redis import Redis
from redis.exceptions import RedisError

from automotive_quality.shared.config import Settings, get_settings

from .auth import AuthenticatedPrincipal
from .authorization import Permission, require_permission

LOGGER = logging.getLogger(__name__)


class OperationCategory(StrEnum):
    AI = "ai"
    JIRA = "jira"
    MUTATION = "mutation"
    READ = "read"


RATE_LIMIT_SCRIPT = """
local current = redis.call('INCR', KEYS[1])
if current == 1 then
  redis.call('PEXPIRE', KEYS[1], ARGV[1])
end
local ttl = redis.call('PTTL', KEYS[1])
return {current, ttl}
"""

ACQUIRE_LEASE_SCRIPT = """
local now = redis.call('TIME')
local now_ms = (now[1] * 1000) + math.floor(now[2] / 1000)
redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', now_ms)
local count = redis.call('ZCARD', KEYS[1])
if count >= tonumber(ARGV[1]) then
  local oldest = redis.call('ZRANGE', KEYS[1], 0, 0, 'WITHSCORES')
  local retry_ms = 1
  if oldest[2] then retry_ms = math.max(1, tonumber(oldest[2]) - now_ms) end
  return {0, retry_ms}
end
redis.call('ZADD', KEYS[1], now_ms + tonumber(ARGV[2]), ARGV[3])
redis.call('PEXPIRE', KEYS[1], tonumber(ARGV[2]) + 1000)
return {1, tonumber(ARGV[2])}
"""

RENEW_LEASE_SCRIPT = """
local score = redis.call('ZSCORE', KEYS[1], ARGV[2])
if not score then return 0 end
local now = redis.call('TIME')
local now_ms = (now[1] * 1000) + math.floor(now[2] / 1000)
redis.call('ZADD', KEYS[1], now_ms + tonumber(ARGV[1]), ARGV[2])
redis.call('PEXPIRE', KEYS[1], tonumber(ARGV[1]) + 1000)
return 1
"""

RELEASE_LEASE_SCRIPT = """
return redis.call('ZREM', KEYS[1], ARGV[1])
"""


@dataclass(frozen=True)
class Admission:
    allowed: bool
    retry_after_seconds: int


@dataclass(frozen=True)
class AdmittedPrincipal(AuthenticatedPrincipal):
    concurrency_lease: "AIConcurrencyLease | None" = None


class RedisRateLimiter:
    def __init__(self, client: Redis, settings: Settings) -> None:
        self.client = client
        self.settings = settings

    def _principal_key(self, principal_id: str) -> str:
        return hashlib.sha256(principal_id.encode("utf-8")).hexdigest()

    def _limit(self, category: OperationCategory) -> int:
        return {
            OperationCategory.AI: self.settings.rate_limit_ai_requests,
            OperationCategory.JIRA: self.settings.rate_limit_jira_requests,
            OperationCategory.MUTATION: self.settings.rate_limit_mutation_requests,
            OperationCategory.READ: self.settings.rate_limit_read_requests,
        }[category]

    def admit(self, principal_id: str, category: OperationCategory) -> Admission:
        window_ms = self.settings.rate_limit_window_seconds * 1000
        # Redis TIME makes every worker choose the same window independent of host clocks.
        seconds, microseconds = self.client.time()
        now_ms = (seconds * 1000) + (microseconds // 1000)
        bucket = now_ms // window_ms
        key = (
            f"{self.settings.rate_limit_namespace}:rate:{category}:"
            f"{self._principal_key(principal_id)}:{bucket}"
        )
        count, ttl_ms = self.client.eval(RATE_LIMIT_SCRIPT, 1, key, window_ms)
        allowed = int(count) <= self._limit(category)
        retry_after = max(1, math.ceil(max(1, int(ttl_ms)) / 1000))
        return Admission(allowed=allowed, retry_after_seconds=retry_after)

    def acquire_ai_lease(self, principal_id: str) -> "AIConcurrencyLease":
        key = (
            f"{self.settings.rate_limit_namespace}:concurrency:ai:"
            f"{self._principal_key(principal_id)}"
        )
        token = uuid4().hex
        lease_ms = self.settings.ai_concurrency_lease_seconds * 1000
        admitted, retry_ms = self.client.eval(
            ACQUIRE_LEASE_SCRIPT,
            1,
            key,
            self.settings.ai_concurrency_per_principal,
            lease_ms,
            token,
        )
        if not int(admitted):
            LOGGER.warning("AI concurrency admission rejected")
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="AI concurrency capacity is temporarily exhausted",
                headers={"Retry-After": str(max(1, math.ceil(int(retry_ms) / 1000)))},
            )
        return AIConcurrencyLease(self.client, key, token, lease_ms)


class AIConcurrencyLease:
    def __init__(self, client: Redis, key: str, token: str, lease_ms: int) -> None:
        self.client = client
        self.key = key
        self.token = token
        self.lease_ms = lease_ms
        self._stopped = threading.Event()
        self._renewal_failed = threading.Event()
        self._thread = threading.Thread(target=self._renew, daemon=True)

    def start(self) -> None:
        self._thread.start()

    @property
    def renewal_failed(self) -> bool:
        return self._renewal_failed.is_set()

    def _renew(self) -> None:
        interval = max(0.1, self.lease_ms / 3000)
        while not self._stopped.wait(interval):
            try:
                renewed = self.client.eval(RENEW_LEASE_SCRIPT, 1, self.key, self.lease_ms, self.token)
                if not int(renewed):
                    self._renewal_failed.set()
                    return
            except RedisError:
                LOGGER.error("AI concurrency lease renewal failed")
                self._renewal_failed.set()
                return

    def release(self) -> None:
        self._stopped.set()
        if self._thread.is_alive():
            self._thread.join(timeout=1)
        try:
            self.client.eval(RELEASE_LEASE_SCRIPT, 1, self.key, self.token)
        except RedisError:
            # The bounded lease remains recoverable even when explicit release cannot reach Redis.
            LOGGER.error("AI concurrency lease release failed")


@lru_cache(maxsize=1)
def get_rate_limiter() -> RedisRateLimiter:
    settings = get_settings()
    client = Redis.from_url(
        settings.redis_url,
        decode_responses=True,
        socket_connect_timeout=1,
        socket_timeout=2,
        health_check_interval=30,
    )
    return RedisRateLimiter(client, settings)


def enforce_rate_limit(
    permission: Permission,
    category: OperationCategory,
    *,
    ai_concurrency: bool = False,
) -> object:
    Authorized = Annotated[AuthenticatedPrincipal, Depends(require_permission(permission))]
    Limiter = Annotated[RedisRateLimiter, Depends(get_rate_limiter)]

    def enforce(principal: Authorized, limiter: Limiter) -> Generator[AuthenticatedPrincipal, None, None]:
        try:
            admission = limiter.admit(principal.principal_id, category)
        except RedisError as exc:
            if category is OperationCategory.READ and get_settings().rate_limit_read_fail_open:
                LOGGER.warning("Read rate limiting is unavailable; applying documented fail-open policy")
                yield principal
                return
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Request admission control is temporarily unavailable",
            ) from exc
        if not admission.allowed:
            LOGGER.warning("Request rate admission rejected for category %s", category)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Request rate limit exceeded",
                headers={"Retry-After": str(admission.retry_after_seconds)},
            )
        lease: AIConcurrencyLease | None = None
        if ai_concurrency:
            try:
                lease = limiter.acquire_ai_lease(principal.principal_id)
                lease.start()
            except RedisError as exc:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="AI capacity control is temporarily unavailable",
                ) from exc
        admitted_principal = AdmittedPrincipal(
            principal_id=principal.principal_id,
            category=principal.category,
            roles=principal.roles,
            key_id=principal.key_id,
            authentication_method=principal.authentication_method,
            concurrency_lease=lease,
        )
        try:
            yield admitted_principal
        finally:
            if lease is not None:
                lease.release()

    enforce.required_permission = permission  # type: ignore[attr-defined]
    enforce.operation_category = category  # type: ignore[attr-defined]
    enforce.ai_concurrency = ai_concurrency  # type: ignore[attr-defined]
    return enforce


def ensure_ai_concurrency_protected(principal: AuthenticatedPrincipal) -> None:
    if isinstance(principal, AdmittedPrincipal):
        lease = principal.concurrency_lease
        if lease is not None and lease.renewal_failed:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="AI concurrency protection was lost during execution",
            )
