from datetime import timedelta

from moiraflow_worker.policies import build_retry_policy


def test_none_retry_uses_bounded_default():
    # No declared retry -> a bounded default so failures can't retry forever.
    policy = build_retry_policy(None)
    assert policy.maximum_attempts == 3


def test_fixed_strategy_has_no_backoff():
    policy = build_retry_policy({"strategy": "fixed", "max_attempts": 3, "interval": "10s"})
    assert policy is not None
    assert policy.maximum_attempts == 3
    assert policy.backoff_coefficient == 1.0
    assert policy.initial_interval == timedelta(seconds=10)


def test_exponential_strategy_has_backoff():
    policy = build_retry_policy(
        {"strategy": "exponential", "max_attempts": 5, "initial_interval": "5s"}
    )
    assert policy is not None
    assert policy.maximum_attempts == 5
    assert policy.backoff_coefficient == 2.0
    assert policy.initial_interval == timedelta(seconds=5)


def test_defaults_when_fields_missing():
    policy = build_retry_policy({"strategy": "fixed"})
    assert policy is not None
    assert policy.maximum_attempts == 1
