from aduib_rpc.client.call_options import RetryOptions, resolve_timeout_s, resolve_retry_options


def test_resolve_timeout_priority_context_over_meta_over_config():
    # context timeout wins
    assert resolve_timeout_s(config_timeout_s=10.0, meta={"timeout_ms": 500}, context_http_kwargs={"timeout": 2}) == 2.0
    # meta ms wins
    assert resolve_timeout_s(config_timeout_s=10.0, meta={"timeout_ms": 500}, context_http_kwargs=None) == 0.5
    # meta s wins
    assert resolve_timeout_s(config_timeout_s=10.0, meta={"timeout_s": 3.5}, context_http_kwargs=None) == 3.5
    # fallback to config
    assert resolve_timeout_s(config_timeout_s=10.0, meta=None, context_http_kwargs=None) == 10.0


def test_resolve_retry_options_defaults_and_overrides():
    defaults = RetryOptions(enabled=False, max_attempts=1)
    # no meta keeps defaults
    assert resolve_retry_options(meta=None, defaults=defaults) == defaults

    r = resolve_retry_options(meta={"retry_enabled": True, "retry_max_attempts": 3, "retry_backoff_ms": 100}, defaults=defaults)
    assert r.enabled is True
    assert r.max_attempts == 3
    assert r.backoff_ms == 100

