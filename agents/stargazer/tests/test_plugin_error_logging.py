from core.plugin.error_logging import PluginExceptionSampler, log_plugin_exception, should_log_plugin_exception


class RecordingLogger:
    def __init__(self):
        self.entries = []

    def error(self, message, *args):
        self.entries.append(message % args if args else message)


def test_plugin_exception_log_has_context_and_sanitized_call_chain():
    logger = RecordingLogger()

    def inner():
        raise RuntimeError("password=must-not-be-logged")

    def outer():
        inner()

    try:
        outer()
    except RuntimeError as error:
        log_plugin_exception(
            logger,
            error=error,
            task_id="task-7",
            plugin_ref="network.config",
            model_id="network",
            plugin_name="snmp_facts",
            target="10.3.252.254",
        )

    assert len(logger.entries) == 1
    entry = logger.entries[0]
    assert "event=plugin_exception" in entry
    assert "task_id=task-7" in entry
    assert "plugin_ref=network.config" in entry
    assert "model_id=network" in entry
    assert "plugin_name=snmp_facts" in entry
    assert "target=10.3.252.254" in entry
    assert "error_type=RuntimeError" in entry
    assert ":outer>" in entry
    assert ":inner" in entry
    assert "password" not in entry
    assert "must-not-be-logged" not in entry
    assert "\n" not in entry


def test_plugin_exception_log_without_traceback_is_still_searchable():
    logger = RecordingLogger()

    log_plugin_exception(
        logger,
        error=RuntimeError("token=must-not-be-logged"),
        task_id="task-8",
        plugin_ref="vmware_vc.config",
        model_id="vmware_vc",
        plugin_name=None,
        target=None,
    )

    assert len(logger.entries) == 1
    assert "plugin_name=-" in logger.entries[0]
    assert "target=logical" in logger.entries[0]
    assert "call_chain=-" in logger.entries[0]
    assert "must-not-be-logged" not in logger.entries[0]


def test_plugin_exception_sampler_limits_the_whole_run():
    params = {"_plugin_exception_sampler": PluginExceptionSampler(limit=3)}

    assert [should_log_plugin_exception(params) for _ in range(5)] == [
        True,
        True,
        True,
        False,
        False,
    ]
