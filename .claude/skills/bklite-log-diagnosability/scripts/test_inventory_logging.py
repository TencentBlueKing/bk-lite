#!/usr/bin/env python3

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from inventory_logging import Finding, render_json, scan_file


class InventoryLoggingTest(unittest.TestCase):
    def _scan(self, source: str):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "sample.py"
            path.write_text(source, encoding="utf-8")
            findings, error = scan_file(path, display_path="sample.py")
        self.assertIsNone(error)
        return findings

    def test_detects_failure_and_noise_candidates(self):
        findings = self._scan(
            '''
import logging
import traceback

logger = logging.getLogger(__name__)

def run(items, payload, password):
    logger.info("=" * 10)
    logger.info(f"payload={payload}")
    logger.info("password=%s", password)
    for item in items:
        logger.info("processing item=%s", item)
    try:
        raise RuntimeError("boom")
    except Exception as exc:
        logger.error(f"failed: {exc}")
        logger.error("trace=%s", traceback.format_exc())
        raise

def swallowed():
    try:
        raise RuntimeError("boom")
    except Exception:
        return []
'''
        )
        rule_ids = {item.rule_id for item in findings}
        self.assertTrue({"L001", "L002", "L003", "L004", "L005", "L006", "L007", "L008", "L009", "L010"} <= rule_ids)

    def test_stable_summary_is_not_flagged(self):
        findings = self._scan(
            '''
import logging

logger = logging.getLogger(__name__)

def complete(task_id, duration_ms):
    logger.info(
        "collection.completed task_id=%s outcome=%s duration_ms=%s",
        task_id,
        "success",
        duration_ms,
    )
'''
        )
        self.assertEqual([], findings)

    def test_bounded_metadata_and_selected_fields_are_not_raw_or_sensitive(self):
        findings = self._scan(
            '''
import logging

logger = logging.getLogger(__name__)

class Client:
    def report(self, token, payload, credential_id):
        logger.info("client.ready token_present=%s", bool(token))
        logger.info(
            "token.policy expires_in_seconds=%s max_usage=%s",
            InfraConstants.TOKEN_EXPIRE_TIME,
            InfraConstants.TOKEN_MAX_USAGE,
        )
        logger.info("client.configured servers=%s", self.config.servers)
        logger.info("request.accepted payload_size=%s", len(payload))
        logger.info("request.accepted task_id=%s", payload.get("task_id"))
        logger.info("credential.selected credential_id=%s", credential_id)
'''
        )
        flagged_rules = {item.rule_id for item in findings}
        self.assertNotIn("L009", flagged_rules)
        self.assertNotIn("L010", flagged_rules)

    def test_only_one_missing_traceback_candidate_per_handler(self):
        findings = self._scan(
            '''
import logging

logger = logging.getLogger(__name__)

try:
    raise RuntimeError("boom")
except Exception:
    logger.error("operation.failed stage=connect")
    logger.error("operation.failed action=retry")
'''
        )
        missing_traceback = [item for item in findings if item.rule_id == "L003"]
        self.assertEqual(1, len(missing_traceback))

    def test_exception_logging_raw_kwargs_is_flagged(self):
        findings = self._scan(
            '''
import logging

logger = logging.getLogger(__name__)

def request(kwargs):
    try:
        raise RuntimeError("boom")
    except Exception:
        logger.exception("request.failed kwargs=%s", kwargs)
'''
        )
        self.assertIn("L009", {item.rule_id for item in findings})

    def test_summary_only_json_omits_individual_findings(self):
        finding = Finding(
            rule_id="L001",
            priority="P2",
            category="formatted-message",
            path="sample.py",
            line=1,
            message="candidate",
            evidence='logger.info(f"value={value}")',
        )
        payload = json.loads(render_json([finding], [], summary_only=True))
        self.assertEqual(1, payload["summary"]["total"])
        self.assertNotIn("findings", payload)


if __name__ == "__main__":
    unittest.main()
