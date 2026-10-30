"""公共部署配置：拒绝无界扩容，消费者及启动命令保持一致。"""

import configparser

import pytest

from apps.core.celery_runtime.config import RuntimeConfig

pytestmark = pytest.mark.unit


def runtime_env(**overrides):
    env = {"ENABLE_CELERY": "true", "CELERY_TOTAL_CONCURRENCY_LIMIT": "7"}
    for pool, maximum in (("CRITICAL", 2), ("NOTIFICATION", 2), ("STATE", 2), ("BACKGROUND", 1)):
        env[f"CELERY_{pool}_MIN"] = "1"
        env[f"CELERY_{pool}_MAX"] = str(maximum)
    return env | overrides


def test_four_consumers_have_independent_bounded_capacity():
    config = RuntimeConfig.from_env(runtime_env())
    commands = [config.worker_args(pool.name) for pool in config.pools]
    assert [c[c.index("-Q") + 1] for c in commands] == ["critical", "notification", "state", "background,celery"]
    assert all("--autoscale=2,1" in c for c in commands[:3])
    assert "--autoscale=1,1" in commands[3]
    assert config.maximum_concurrency == 7


@pytest.mark.parametrize(
    "overrides",
    [
        {"CELERY_STATE_MIN": "0"},
        {"CELERY_STATE_MIN": "3"},
        {"CELERY_STATE_MAX": ""},
        {"CELERY_STATE_MAX": "1.5"},
        {"CELERY_TOTAL_CONCURRENCY_LIMIT": "6"},
        {"CELERY_CONCURRENCY": "4"},
        {"CELERY_WORKER_REPLICAS": "2"},
        {"AUTOSCALE_KEEPALIVE": "0"},
        {"ENABLE_CELERY": "tru"},
    ],
)
def test_invalid_or_over_budget_configuration_fails_before_start(overrides):
    with pytest.raises(ValueError):
        RuntimeConfig.from_env(runtime_env(**overrides))


def test_budget_counts_all_replicas_at_maximum():
    config = RuntimeConfig.from_env(runtime_env(CELERY_WORKER_REPLICAS="2", CELERY_TOTAL_CONCURRENCY_LIMIT="14", CELERY_RUN_BEAT="false"))
    assert config.maximum_concurrency == 14
    assert "[program:beat]" not in config.supervisor_config()


def test_multiple_replicas_require_explicit_beat_owner():
    with pytest.raises(ValueError, match="CELERY_RUN_BEAT"):
        RuntimeConfig.from_env(runtime_env(CELERY_WORKER_REPLICAS="2", CELERY_TOTAL_CONCURRENCY_LIMIT="14"))


def test_missing_budget_is_not_inferred_from_cpu_count():
    env = runtime_env()
    del env["CELERY_TOTAL_CONCURRENCY_LIMIT"]
    with pytest.raises(ValueError, match="CELERY_TOTAL_CONCURRENCY_LIMIT"):
        RuntimeConfig.from_env(env)


def test_disabled_celery_needs_no_capacity_and_generates_no_programs():
    config = RuntimeConfig.from_env({"ENABLE_CELERY": "false"})
    assert config.pools == ()
    assert "[program:" not in config.supervisor_config()
    with pytest.raises(ValueError):
        config.worker_args("critical")


def test_supervisor_has_only_four_workers_and_one_beat():
    parser = configparser.ConfigParser(interpolation=None)
    parser.read_string(RuntimeConfig.from_env(runtime_env()).supervisor_config())
    assert set(parser.sections()) == {
        "program:celery_critical",
        "program:celery_notification",
        "program:celery_state",
        "program:celery_background",
        "program:beat",
    }
    for section in parser.sections():
        assert parser[section]["stopsignal"] == "TERM"
        assert parser[section]["stopasgroup"] == "false"
    assert "critical@%%h" in parser["program:celery_critical"]["command"]
    assert 'AUTOSCALE_KEEPALIVE="60"' in parser["program:celery_critical"]["environment"]


def test_unknown_pool_is_rejected():
    with pytest.raises(ValueError):
        RuntimeConfig.from_env(runtime_env()).worker_args("typo")
