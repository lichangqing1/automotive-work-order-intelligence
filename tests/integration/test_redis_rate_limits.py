from __future__ import annotations

import os
import time
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from fastapi import HTTPException
from redis import Redis

from automotive_quality.api.auth import AuthenticatedPrincipal
from automotive_quality.api.authorization import Permission
from automotive_quality.api.rate_limits import OperationCategory, RedisRateLimiter, enforce_rate_limit
from automotive_quality.shared.config import Settings

pytestmark = pytest.mark.redis


@pytest.fixture
def redis_limiters() -> tuple[RedisRateLimiter, RedisRateLimiter, Redis, str]:
    url = os.getenv("REDIS_TEST_URL")
    if not url:
        pytest.skip("REDIS_TEST_URL is not configured")
    namespace = f"automotive-quality-test:{uuid4().hex}"
    client_a = Redis.from_url(url, decode_responses=True, socket_timeout=2)
    client_b = Redis.from_url(url, decode_responses=True, socket_timeout=2)
    client_a.ping()
    settings = Settings(
        redis_url=url,
        rate_limit_namespace=namespace,
        rate_limit_window_seconds=1,
        rate_limit_ai_requests=10,
        rate_limit_jira_requests=10,
        rate_limit_mutation_requests=30,
        rate_limit_read_requests=120,
        ai_concurrency_per_principal=2,
        ai_concurrency_lease_seconds=1,
    )
    try:
        yield RedisRateLimiter(client_a, settings), RedisRateLimiter(client_b, settings), client_a, namespace
    finally:
        keys = list(client_a.scan_iter(match=f"{namespace}:*"))
        if keys:
            client_a.delete(*keys)
        client_a.close()
        client_b.close()


def test_real_redis_atomic_rate_boundary_independent_principals_and_expiry(redis_limiters) -> None:
    limiter_a, limiter_b, client, namespace = redis_limiters

    def attempt(index: int) -> bool:
        limiter = limiter_a if index % 2 else limiter_b
        return limiter.admit("shared-principal", OperationCategory.AI).allowed

    with ThreadPoolExecutor(max_workers=20) as pool:
        outcomes = list(pool.map(attempt, range(20)))
    assert outcomes.count(True) == 10
    assert outcomes.count(False) == 10
    assert limiter_a.admit("independent-principal", OperationCategory.AI).allowed
    assert list(client.scan_iter(match=f"{namespace}:rate:ai:*"))
    time.sleep(1.1)
    assert limiter_b.admit("shared-principal", OperationCategory.AI).allowed


def test_real_redis_concurrency_admission_token_release_renewal_and_recovery(redis_limiters) -> None:
    limiter_a, limiter_b, client, namespace = redis_limiters
    first = limiter_a.acquire_ai_lease("shared-principal")
    second = limiter_b.acquire_ai_lease("shared-principal")
    first.start()
    second.start()
    with pytest.raises(HTTPException) as rejected:
        limiter_b.acquire_ai_lease("shared-principal")
    assert rejected.value.status_code == 429
    assert rejected.value.detail == "AI concurrency capacity is temporarily exhausted"

    # Heartbeats keep both one-second leases present beyond their initial expiry.
    time.sleep(1.2)
    keys = list(client.scan_iter(match=f"{namespace}:concurrency:ai:*"))
    assert len(keys) == 1 and client.zcard(keys[0]) == 2
    first.release()
    replacement = limiter_b.acquire_ai_lease("shared-principal")
    replacement.start()
    assert client.zcard(keys[0]) == 2

    # Simulate a worker interruption by stopping renewal without releasing its token.
    second._stopped.set()
    second._thread.join(timeout=1)
    replacement.release()
    time.sleep(1.1)
    recovered = limiter_a.acquire_ai_lease("shared-principal")
    recovered.start()
    assert client.zcard(keys[0]) == 1
    recovered.release()


def test_real_client_connection_outage_maps_to_fail_closed_and_documented_read_policy() -> None:
    settings = Settings(
        redis_url="redis://127.0.0.1:1/0",
        rate_limit_namespace=f"automotive-quality-test:{uuid4().hex}",
    )
    unavailable = Redis.from_url(
        settings.redis_url,
        decode_responses=True,
        socket_connect_timeout=0.05,
        socket_timeout=0.05,
    )
    limiter = RedisRateLimiter(unavailable, settings)
    principal = AuthenticatedPrincipal(
        principal_id="outage-test-principal",
        category="test",
        roles=frozenset({"operator"}),
        key_id="outage-test-key",
    )

    ai_guard = enforce_rate_limit(Permission.OPERATE_AI, OperationCategory.AI, ai_concurrency=True)
    with pytest.raises(HTTPException) as unavailable_ai:
        next(ai_guard(principal, limiter))
    assert unavailable_ai.value.status_code == 503
    assert unavailable_ai.value.detail == "Request admission control is temporarily unavailable"

    read_guard = enforce_rate_limit(Permission.READ, OperationCategory.READ)
    readable = read_guard(principal, limiter)
    assert next(readable) == principal
    with pytest.raises(StopIteration):
        next(readable)
    unavailable.close()
