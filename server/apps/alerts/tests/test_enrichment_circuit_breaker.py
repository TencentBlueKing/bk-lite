from apps.alerts.enrichment.circuit_breaker import CircuitBreaker


class _Cache:
    def __init__(self):
        self.values = {}

    def get(self, key, default=None):
        return self.values.get(key, default)

    def set(self, key, value, timeout=None):
        self.values[key] = value

    def add(self, key, value, timeout=None):
        if key in self.values:
            return False
        self.values[key] = value
        return True

    def delete(self, key):
        self.values.pop(key, None)

    def incr(self, key):
        self.values[key] += 1
        return self.values[key]


def test_open_requests_do_not_extend_retry_time():
    now = [100.0]
    cache = _Cache()
    breaker = CircuitBreaker(cache_backend=cache, clock=lambda: now[0], failure_threshold=1, open_seconds=30)

    first = breaker.before_call("cmdb:team-1")
    breaker.after_call("cmdb:team-1", first, success=False)
    retry_at = cache.get("cmdb:team-1")["retry_at"]

    now[0] = 110.0
    assert breaker.before_call("cmdb:team-1").allowed is False
    now[0] = 125.0
    assert breaker.before_call("cmdb:team-1").allowed is False
    assert cache.get("cmdb:team-1")["retry_at"] == retry_at


def test_only_one_half_open_probe_is_allowed_and_success_closes_breaker():
    now = [100.0]
    cache = _Cache()
    breaker = CircuitBreaker(cache_backend=cache, clock=lambda: now[0], failure_threshold=1, open_seconds=30)

    decision = breaker.before_call("cmdb:team-1")
    breaker.after_call("cmdb:team-1", decision, success=False)
    now[0] = 131.0

    probe = breaker.before_call("cmdb:team-1")
    concurrent = breaker.before_call("cmdb:team-1")

    assert probe.allowed is True
    assert probe.is_probe is True
    assert concurrent.allowed is False

    breaker.after_call("cmdb:team-1", probe, success=True)
    assert cache.get("cmdb:team-1") is None
    assert breaker.before_call("cmdb:team-1").allowed is True


def test_not_found_success_does_not_open_breaker():
    now = [100.0]
    cache = _Cache()
    breaker = CircuitBreaker(cache_backend=cache, clock=lambda: now[0], failure_threshold=1, open_seconds=30)

    decision = breaker.before_call("cmdb:team-1")
    breaker.after_call("cmdb:team-1", decision, success=True)

    assert cache.get("cmdb:team-1") is None
    assert breaker.before_call("cmdb:team-1").allowed is True
