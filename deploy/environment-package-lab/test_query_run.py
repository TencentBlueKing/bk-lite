import json
import tempfile
import unittest
from pathlib import Path
from query_run import match_receipts, verified_run, find_alert_row


def events(prefix):
    return [
        {
            "pusher": p,
            "alert_id": prefix + p + str(i),
            "event_id": prefix + p + str(i) + action,
            "payload": {
                "external_id": prefix + p + str(i),
                "event_key": prefix + p + str(i) + action if p == "lite-apm" else "",
                "action": action,
                "start_time": "123",
                "end_time": None,
                "resource_id": str(i),
                "rule_id": "1",
            },
        }
        for p, actions in [("lite-log", ["created", "closed"]), ("lite-apm", ["triggered", "recovered"])]
        for i in range(2)
        for action in actions
    ]


def receipts(expected):
    return [{"pusher": x["pusher"], "event": x["payload"]} for x in expected]


class RunTest(unittest.TestCase):
    def test_log_query_uses_injection_window_even_when_acceptance_is_delayed(self):
        from query_run import log_query_route
        from urllib.parse import urlparse, parse_qs
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            traffic = [{"ip": ip, "marker": "CD-QUERY-alarm-1800000000-env-auto-" + node + "-20261114"} for node, ip in [("c", "192.168.122.4"), ("d", "192.168.122.209")]]
            (out / "alarm-traffic.json").write_text(json.dumps(traffic))
            params = parse_qs(urlparse(log_query_route(out)).query)
            self.assertEqual(params["startTime"], ["1799999940000"])
            self.assertEqual(params["endTime"], ["1800000120000"])
            self.assertEqual(params["log_groups"], ["cd-query-validation"])
            self.assertEqual(params["query"], ['verification:="CD-QUERY"'])
            traffic[1]["marker"] = "CD-QUERY-alarm-1800000001-env-auto-d-20261114"
            (out / "alarm-traffic.json").write_text(json.dumps(traffic))
            with self.assertRaises(AssertionError):
                log_query_route(out)

    def test_second_run_joins_only_current_event_ids(self):
        current = events("new")
        actual = match_receipts(current, receipts(events("old")) + receipts(current))
        self.assertEqual({x["event_id"] for x in actual}, {x["event_id"] for x in current})

    def test_old_success_cannot_cover_missing_current_run(self):
        with self.assertRaises(AssertionError):
            match_receipts(events("new"), receipts(events("old")))

    def test_same_counts_wrong_event_or_duplicate_are_rejected(self):
        for mode in ["old", "duplicate", "wrong_time", "wrong_event_key"]:
            with self.subTest(mode=mode):
                current = events("new")
                actual = receipts(current)
                if mode == "old":
                    actual[-1] = receipts(events("old"))[-1]
                elif mode == "duplicate":
                    actual[-1] = actual[0]
                elif mode == "wrong_time":
                    actual[-1] = {**actual[-1], "event": {**actual[-1]["event"], "start_time": "999"}}
                else:
                    actual[-1] = {**actual[-1], "event": {**actual[-1]["event"], "event_key": "old-event"}}
                with self.assertRaises(AssertionError):
                    match_receipts(current, actual)

    def test_stale_verification_cannot_drive_ui(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            (out / "alarm-traffic.json").write_text(
                json.dumps(
                    [
                        {"ip": ip, "marker": "CD-QUERY-alarm-1800000000-env-auto-" + node + "-20261114"}
                        for node, ip in [("c", "192.168.122.4"), ("d", "192.168.122.209")]
                    ]
                )
            )
            (out / "final-verification.json").write_text(json.dumps({"passed": True, "run_id": "old"}))
            with self.assertRaises(AssertionError):
                verified_run(out)


class Locator:
    def __init__(self, page, selector):
        self.page, self.selector = page, selector

    def count(self):
        if self.selector.startswith("tr["):
            return int(self.selector in self.page.pages[self.page.index])
        return int(self.page.index + 1 < len(self.page.pages))

    def click(self):
        self.page.index += 1


class Page:
    def __init__(self):
        # Same policy name on both pages; only the exact current key is eligible.
        self.pages = [{'tr[data-row-key="aaaa"]': "C/D 延迟验证 cd-c"}, {'tr[data-row-key="bbbb"]': "C/D 延迟验证 cd-c"}]
        self.index = 0

    def locator(self, selector):
        return Locator(self, selector)

    def wait_for_load_state(self, state):
        pass

    def wait_for_timeout(self, duration):
        pass


class RowTest(unittest.TestCase):
    def test_duplicate_policy_names_select_current_id_across_pages(self):
        page = Page()
        row = find_alert_row(page, "bbbb")
        self.assertEqual(row.selector, 'tr[data-row-key="bbbb"]')
        self.assertEqual(page.index, 1)

    def test_missing_current_id_never_uses_old_row(self):
        with self.assertRaises(AssertionError):
            find_alert_row(Page(), "cccc")


if __name__ == "__main__":
    unittest.main()
