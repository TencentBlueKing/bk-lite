from core.plugin.error_logging import PluginExceptionLogBudget, log_plugin_exception, should_log_plugin_exception


class RecordingLogger:
    def __init__(self):
        self.entries = []

    def error(self, message, *args):
        self.entries.append(message % args if args else message)


def test_plugin_exception_log_has_context_and_sanitized_call_chain():
    logger = RecordingLogger()

    def inner():
        sensitive_message = "password=must-not-be-logged"
        raise RuntimeError(sensitive_message)

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
    assert "source_context=" in entry
    assert "outer()" in entry
    assert "raise RuntimeError(sensitive_message)" in entry
    assert "password" not in entry
    assert "must-not-be-logged" not in entry
    assert "\n" in entry


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
    assert "source_context=\n-" in logger.entries[0]
    assert "must-not-be-logged" not in logger.entries[0]


def test_plugin_exception_log_includes_safe_error_message():
    logger = RecordingLogger()

    try:
        raise RuntimeError("SNMP authorization failure for 10.3.252.254")
    except RuntimeError as error:
        log_plugin_exception(
            logger,
            error=error,
            task_id="task-9",
            plugin_ref="network.config",
            model_id="network",
            plugin_name="snmp_facts",
            target="10.3.252.254",
        )

    assert "error_message=SNMP authorization failure for 10.3.252.254" in logger.entries[0]


def test_plugin_exception_logging_follows_target_context_flag():
    assert should_log_plugin_exception({"_log_plugin_call_chain": True}) is True
    assert should_log_plugin_exception({"_log_plugin_call_chain": False}) is False
    assert should_log_plugin_exception({}) is False


def test_plugin_exception_log_budget_is_shared_and_bounded():
    budget = PluginExceptionLogBudget(limit=3)
    params = {
        "_log_plugin_call_chain": True,
        "_plugin_exception_log_budget": budget,
    }

    assert [should_log_plugin_exception(params) for _ in range(5)] == [
        True,
        True,
        True,
        False,
        False,
    ]
