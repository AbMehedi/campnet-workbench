"""Redis client access."""

from functools import lru_cache

from redis import Redis


@lru_cache
def request_redis_client(url: str) -> Redis:
    """Client for short request-path calls (e.g. readiness pings).

    Short socket timeouts so a request can never hang. Not for blocking commands (BLPOP / RQ
    workers): those need their own client without ``socket_timeout``.
    """
    return Redis.from_url(url, socket_connect_timeout=2, socket_timeout=2)
