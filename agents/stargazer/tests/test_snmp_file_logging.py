import logging

from core.infra.snmp_file_logging import configure_snmp_file_logging, snmp_log_scope


def test_snmp_file_only_receives_network_collection_and_scoped_plugin_logs(tmp_path):
    log_path = tmp_path / "snmp_facts.log"
    test_logger = logging.getLogger("test.stargazer.snmp-file")
    test_logger.handlers.clear()
    test_logger.propagate = False
    test_logger.setLevel(logging.INFO)
    handler = configure_snmp_file_logging(
        log_path=log_path,
        target_logger=test_logger,
        max_bytes=1024 * 1024,
        backup_count=2,
    )

    try:
        test_logger.info("event=collection_run_started plugin_ref=mysql.config plugin_name=mysql_info")
        test_logger.info("event=collection_run_started plugin_ref=network.config plugin_name=snmp_facts")
        with snmp_log_scope(True):
            test_logger.warning("SNMP topology raw warning target=10.10.69.245")
        for item in test_logger.handlers:
            item.flush()
    finally:
        if handler is not None:
            handler.close()
            test_logger.removeHandler(handler)

    content = log_path.read_text(encoding="utf-8")
    assert "plugin_ref=network.config" in content
    assert "SNMP topology raw warning" in content
    assert "plugin_ref=mysql.config" not in content


def test_snmp_file_logging_is_idempotent(tmp_path):
    test_logger = logging.getLogger("test.stargazer.snmp-file-idempotent")
    test_logger.handlers.clear()
    test_logger.propagate = False
    first = configure_snmp_file_logging(
        log_path=tmp_path / "snmp.log",
        target_logger=test_logger,
    )
    second = configure_snmp_file_logging(
        log_path=tmp_path / "snmp.log",
        target_logger=test_logger,
    )

    try:
        assert first is second
        assert len(test_logger.handlers) == 1
    finally:
        if first is not None:
            first.close()
            test_logger.removeHandler(first)
