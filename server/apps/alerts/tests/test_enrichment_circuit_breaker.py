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


def test_closed_success_clears_failure_counter_below_threshold():
    now = [100.0]
    cache = _Cache()
    breaker = CircuitBreaker(cache_backend=cache, clock=lambda: now[0], failure_threshold=2, open_seconds=30)

    first = breaker.before_call("cmdb:team-1")
    breaker.after_call("cmdb:team-1", first, success=False)
    assert cache.get("cmdb:team-1:failures") == 1

    closed = breaker.before_call("cmdb:team-1")
    breaker.after_call("cmdb:team-1", closed, success=True)

    assert cache.get("cmdb:team-1") is None
    assert cache.get("cmdb:team-1:failures") is None
    again = breaker.before_call("cmdb:team-1")
    breaker.after_call("cmdb:team-1", again, success=False)
    assert cache.get("cmdb:team-1") is None


def test_late_closed_success_does_not_clear_open_window():
    now = [100.0]
    cache = _Cache()
    breaker = CircuitBreaker(cache_backend=cache, clock=lambda: now[0], failure_threshold=2, open_seconds=30)

    first = breaker.before_call("cmdb:team-1")
    second = breaker.before_call("cmdb:team-1")
    late = breaker.before_call("cmdb:team-1")
    breaker.after_call("cmdb:team-1", first, success=False)
    breaker.after_call("cmdb:team-1", second, success=False)
    retry_at = cache.get("cmdb:team-1")["retry_at"]

    breaker.after_call("cmdb:team-1", late, success=True)

    assert breaker.before_call("cmdb:team-1").allowed is False
    assert cache.get("cmdb:team-1")["status"] == "open"
    assert cache.get("cmdb:team-1")["retry_at"] == retry_at


def test_non_probe_failure_does_not_replace_open_window():
    now = [100.0]
    cache = _Cache()
    breaker = CircuitBreaker(cache_backend=cache, clock=lambda: now[0], failure_threshold=2, open_seconds=30)

    first = breaker.before_call("cmdb:team-1")
    second = breaker.before_call("cmdb:team-1")
    late = breaker.before_call("cmdb:team-1")
    breaker.after_call("cmdb:team-1", first, success=False)
    breaker.after_call("cmdb:team-1", second, success=False)
    retry_at = cache.get("cmdb:team-1")["retry_at"]

    now[0] = 110.0
    breaker.after_call("cmdb:team-1", late, success=False)

    assert cache.get("cmdb:team-1")["status"] == "open"
    assert cache.get("cmdb:team-1")["retry_at"] == retry_at
    assert breaker.before_call("cmdb:team-1").allowed is False


def test_stale_probe_does_not_mutate_newer_window_and_current_probe_closes():
    now = [100.0]
    cache = _Cache()
    breaker = CircuitBreaker(cache_backend=cache, clock=lambda: now[0], failure_threshold=1, open_seconds=30)

    opened = breaker.before_call("cmdb:team-1")
    breaker.after_call("cmdb:team-1", opened, success=False)
    now[0] = 131.0
    stale_success = breaker.before_call("cmdb:team-1")
    assert stale_success.is_probe is True
    replaced_retry_at = 200.0
    cache.set("cmdb:team-1", {"status": "open", "retry_at": replaced_retry_at})

    breaker.after_call("cmdb:team-1", stale_success, success=True)
    assert cache.get("cmdb:team-1") == {"status": "open", "retry_at": replaced_retry_at}

    now[0] = 201.0
    stale_failure = breaker.before_call("cmdb:team-1")
    assert stale_failure.is_probe is True
    newer_retry_at = 280.0
    cache.set("cmdb:team-1", {"status": "open", "retry_at": newer_retry_at})

    breaker.after_call("cmdb:team-1", stale_failure, success=False)
    assert cache.get("cmdb:team-1") == {"status": "open", "retry_at": newer_retry_at}

    now[0] = 281.0
    current = breaker.before_call("cmdb:team-1")
    assert current.is_probe is True
    breaker.after_call("cmdb:team-1", current, success=True)
    assert cache.get("cmdb:team-1") is None
    assert breaker.before_call("cmdb:team-1").allowed is True


def test_current_probe_failure_opens_a_new_window():
    now = [100.0]
    cache = _Cache()
    breaker = CircuitBreaker(cache_backend=cache, clock=lambda: now[0], failure_threshold=1, open_seconds=30)

    opened = breaker.before_call("cmdb:team-1")
    breaker.after_call("cmdb:team-1", opened, success=False)
    now[0] = 131.0
    probe = breaker.before_call("cmdb:team-1")
    assert probe.is_probe is True

    breaker.after_call("cmdb:team-1", probe, success=False)

    assert cache.get("cmdb:team-1")["status"] == "open"
    assert cache.get("cmdb:team-1")["retry_at"] == 161.0
    assert breaker.before_call("cmdb:team-1").allowed is False
