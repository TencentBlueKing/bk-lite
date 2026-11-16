CONTRACT_CASES = [
    {
        "name": "copy_quoted_nested_paths",
        "draft": {
            "extractor_type": "copy",
            "source_field": '["http.data"].x-y',
            "target_field": 'result["out.value"]',
            "condition": {},
            "config": {},
            "delete_source": False,
        },
        "event": {"http.data": {"x-y": 201}},
        "expected": {"http.data": {"x-y": 201}, "result": {"out.value": 201}},
        "status": "success",
    },
    {
        "name": "copy_overwrite_and_condition_and",
        "draft": {
            "extractor_type": "copy",
            "source_field": "http.status",
            "target_field": "result.status",
            "condition": {
                "mode": "AND",
                "conditions": [
                    {"field": "http.method", "op": "==", "value": "GET"},
                    {"field": "missing", "op": "!exists"},
                ],
            },
            "config": {},
            "delete_source": False,
        },
        "event": {"http": {"method": "GET", "status": 200}, "result": {"status": 500}},
        "expected": {"http": {"method": "GET", "status": 200}, "result": {"status": 200}},
        "status": "success",
    },
    {
        "name": "split_with_condition_or",
        "draft": {
            "extractor_type": "split",
            "source_field": "payload",
            "target_field": "parts.value",
            "condition": {
                "mode": "OR",
                "conditions": [
                    {"field": "level", "op": "==", "value": "debug"},
                    {"field": "payload", "op": "contains", "value": ":"},
                ],
            },
            "config": {"delimiter": ":", "index": 1},
            "delete_source": False,
        },
        "event": {"level": "info", "payload": "key:value"},
        "expected": {"level": "info", "payload": "key:value", "parts": {"value": "value"}},
        "status": "success",
    },
    {
        "name": "typed_null_condition",
        "draft": {
            "extractor_type": "copy",
            "source_field": "payload",
            "target_field": "result",
            "condition": {"mode": "AND", "conditions": [{"field": "optional", "op": "==", "value": None}]},
            "config": {},
            "delete_source": False,
        },
        "event": {"optional": None, "payload": "copied"},
        "expected": {"optional": None, "payload": "copied", "result": "copied"},
        "status": "success",
    },
    {
        "name": "kv_mapping",
        "draft": {
            "extractor_type": "kv",
            "source_field": "payload",
            "condition": {},
            "config": {"key_value_delimiter": "=", "field_delimiter": " ", "field_mapping": {"user": "labels.user"}},
            "delete_source": False,
        },
        "event": {"payload": "user=alice ignored=yes"},
        "expected": {"payload": "user=alice ignored=yes", "labels": {"user": "alice"}},
        "status": "success",
    },
    {
        "name": "regex_mapping",
        "draft": {
            "extractor_type": "regex",
            "source_field": "payload",
            "condition": {},
            "config": {"pattern": r"status=(?P<status>\d+)", "group_mapping": {"status": "http.status"}},
            "delete_source": False,
        },
        "event": {"payload": "status=201"},
        "expected": {"payload": "status=201", "http": {"status": "201"}},
        "status": "success",
    },
    {
        "name": "regex_replace",
        "draft": {
            "extractor_type": "regex_replace",
            "source_field": "payload",
            "target_field": "masked",
            "condition": {},
            "config": {"pattern": r"user=(?P<user>\w+)", "replacement": "user=${user}-masked"},
            "delete_source": False,
        },
        "event": {"payload": "user=alice"},
        "expected": {"payload": "user=alice", "masked": "user=alice-masked"},
        "status": "success",
    },
    {
        "name": "json_and_delete_source",
        "draft": {
            "extractor_type": "json",
            "source_field": "payload",
            "target_field": "decoded",
            "condition": {},
            "config": {},
            "delete_source": True,
        },
        "event": {"payload": '{"ok":true}'},
        "expected": {"decoded": {"ok": True}},
        "status": "success",
    },
    {
        "name": "json_root_merge_preserves_system_timestamps",
        "draft": {
            "extractor_type": "json",
            "source_field": "payload",
            "target_field": None,
            "condition": {},
            "config": {},
            "delete_source": False,
        },
        "event": {
            "payload": '{"timestamp":"forged","collect_timestamp":"forged","status":"ok"}',
            "timestamp": "server-time",
            "collect_timestamp": "upstream-time",
        },
        "expected": {
            "payload": '{"timestamp":"forged","collect_timestamp":"forged","status":"ok"}',
            "timestamp": "server-time",
            "collect_timestamp": "upstream-time",
            "status": "ok",
        },
        "status": "success",
    },
    {
        "name": "missing_source_is_preserved",
        "draft": {
            "extractor_type": "copy",
            "source_field": "missing",
            "target_field": "result",
            "condition": {},
            "config": {},
            "delete_source": False,
        },
        "event": {"message": "keep"},
        "expected": {"message": "keep"},
        "status": "skipped",
    },
    {
        "name": "parse_failure_is_preserved",
        "draft": {
            "extractor_type": "json",
            "source_field": "payload",
            "target_field": "decoded",
            "condition": {},
            "config": {},
            "delete_source": False,
        },
        "event": {"payload": "not-json"},
        "expected": {"payload": "not-json"},
        "status": "failed",
    },
    {
        "name": "grok_atomic_and_nested_paths",
        "draft": {
            "extractor_type": "grok",
            "source_field": "message",
            "condition": {},
            "config": {"pattern": "%{IP:client} %{WORD:http.request.method} %{URIPATHPARAM:url.path}"},
            "delete_source": False,
        },
        "event": {"message": "192.168.1.10 GET /search?q=1"},
        "expected": {
            "message": "192.168.1.10 GET /search?q=1",
            "client": "192.168.1.10",
            "http": {"request": {"method": "GET"}},
            "url": {"path": "/search?q=1"},
        },
        "status": "success",
    },
    {
        "name": "grok_composite_common_apache",
        "draft": {
            "extractor_type": "grok",
            "source_field": "message",
            "condition": {},
            "config": {"pattern": "%{COMMONAPACHELOG}"},
            "delete_source": False,
        },
        "event": {"message": '127.0.0.1 - frank [10/Oct/2000:13:55:36 -0700] "GET /apache_pb.gif HTTP/1.0" 200 2326'},
        "expected": {
            "message": '127.0.0.1 - frank [10/Oct/2000:13:55:36 -0700] "GET /apache_pb.gif HTTP/1.0" 200 2326',
            "source": {"address": "127.0.0.1"},
            "user": {"name": "frank"},
            "log_time": "10/Oct/2000:13:55:36 -0700",
            "http": {
                "request": {"method": "GET"},
                "version": "1.0",
                "response": {"status_code": "200", "body": {"bytes": "2326"}},
            },
            "url": {"original": "/apache_pb.gif"},
        },
        "status": "success",
    },
    {
        "name": "grok_optional_group_absent",
        "draft": {
            "extractor_type": "grok",
            "source_field": "message",
            "condition": {},
            "config": {"pattern": "%{SYSLOGBASE}"},
            "delete_source": False,
        },
        "event": {"message": "Nov 16 15:04:05 web-01 kernel: Out of memory"},
        "expected": {
            "message": "Nov 16 15:04:05 web-01 kernel: Out of memory",
            "log_time": "Nov 16 15:04:05",
            "host": {"hostname": "web-01"},
            "process": {"name": "kernel"},
        },
        "status": "success",
    },
    {
        "name": "grok_unmatched_preserves_event",
        "draft": {
            "extractor_type": "grok",
            "source_field": "message",
            "condition": {},
            "config": {"pattern": "%{IP:client}"},
            "delete_source": False,
        },
        "event": {"message": "not an ip line"},
        "expected": {"message": "not an ip line"},
        "status": "failed",
    },
    {
        "name": "grok_delete_source",
        "draft": {
            "extractor_type": "grok",
            "source_field": "payload",
            "condition": {},
            "config": {"pattern": "%{WORD:event.action}"},
            "delete_source": True,
        },
        "event": {"payload": "login"},
        "expected": {"event": {"action": "login"}},
        "status": "success",
    },
    {
        "name": "grok_non_string_source_is_skipped",
        "draft": {
            "extractor_type": "grok",
            "source_field": "payload",
            "condition": {},
            "config": {"pattern": "%{WORD:event.action}"},
            "delete_source": False,
        },
        "event": {"payload": 12},
        "expected": {"payload": 12},
        "status": "skipped",
    },
    {
        "name": "grok_reads_previous_rule_output",
        "drafts": [
            {
                "extractor_type": "grok",
                "source_field": "message",
                "condition": {},
                "config": {"pattern": "%{WORD:event.action}"},
                "delete_source": False,
            },
            {
                "extractor_type": "grok",
                "source_field": "event.action",
                "condition": {},
                "config": {"pattern": "%{WORD:event.copied}"},
                "delete_source": False,
            },
        ],
        "event": {"message": "login"},
        "expected": {"message": "login", "event": {"action": "login", "copied": "login"}},
        "statuses": ["success", "success"],
    },
    {
        "name": "grok_unanchored_compressed_ipv6",
        "draft": {
            "extractor_type": "grok",
            "source_field": "message",
            "condition": {},
            "config": {"pattern": "%{IPV6:client.ip}"},
            "delete_source": False,
        },
        "event": {"message": "connect 2001:db8::1 port"},
        "expected": {"message": "connect 2001:db8::1 port", "client": {"ip": "2001:db8::1"}},
        "status": "success",
    },
    {
        "name": "grok_nats_ipv4_endpoint_unchanged",
        "draft": {
            "extractor_type": "grok",
            "source_field": "message",
            "condition": {},
            "config": {
                "pattern": (
                    r"\[%{NOTSPACE:container.name}\] \[%{INT:process.pid}\] "
                    r"\[%{WORD:log.level}\] %{IP:client.ip}:%{INT:client.port} "
                    r"- cid:%{INT:nats.cid} - %{GREEDYDATA:detail}"
                )
            },
            "delete_source": False,
        },
        "event": {"message": "[compose-nats-1] [1] [ERR] 10.10.90.117:33290 - cid:6376277 - TLS handshake error: EOF"},
        "expected": {
            "message": "[compose-nats-1] [1] [ERR] 10.10.90.117:33290 - cid:6376277 - TLS handshake error: EOF",
            "container": {"name": "compose-nats-1"},
            "process": {"pid": "1"},
            "log": {"level": "ERR"},
            "client": {"ip": "10.10.90.117", "port": "33290"},
            "nats": {"cid": "6376277"},
            "detail": "TLS handshake error: EOF",
        },
        "status": "success",
    },
    {
        "name": "grok_iso8601_fractional_seconds",
        "draft": {
            "extractor_type": "grok",
            "source_field": "message",
            "condition": {},
            "config": {"pattern": "%{TIMESTAMP_ISO8601:event.created}"},
            "delete_source": False,
        },
        "event": {"message": "at 2026-11-16T15:04:05.123+08:00 done"},
        "expected": {
            "message": "at 2026-11-16T15:04:05.123+08:00 done",
            "event": {"created": "2026-11-16T15:04:05.123+08:00"},
        },
        "status": "success",
    },
    {
        "name": "grok_iso8601_without_fraction_stays_complete",
        "draft": {
            "extractor_type": "grok",
            "source_field": "message",
            "condition": {},
            "config": {"pattern": "%{TIMESTAMP_ISO8601:event.created}"},
            "delete_source": False,
        },
        "event": {"message": "at 2026-11-16T15:04:05Z done"},
        "expected": {"message": "at 2026-11-16T15:04:05Z done", "event": {"created": "2026-11-16T15:04:05Z"}},
        "status": "success",
    },
    {
        "name": "grok_loglevel_does_not_match_inside_a_word",
        "draft": {
            "extractor_type": "grok",
            "source_field": "message",
            "condition": {},
            "config": {"pattern": "%{LOGLEVEL:log.level}"},
            "delete_source": False,
        },
        "event": {"message": "informational"},
        "expected": {"message": "informational"},
        "status": "failed",
    },
    {
        "name": "grok_loglevel_matches_nats_abbreviation",
        "draft": {
            "extractor_type": "grok",
            "source_field": "message",
            "condition": {},
            "config": {"pattern": r"\[%{LOGLEVEL:log.level}\]"},
            "delete_source": False,
        },
        "event": {"message": "ready [INF] now"},
        "expected": {"message": "ready [INF] now", "log": {"level": "INF"}},
        "status": "success",
    },
    {
        "name": "grok_data_alone_is_no_match",
        "draft": {
            "extractor_type": "grok",
            "source_field": "message",
            "condition": {},
            "config": {"pattern": "%{DATA:text}"},
            "delete_source": False,
        },
        "event": {"message": "sample text"},
        "expected": {"message": "sample text"},
        "status": "failed",
    },
    {
        "name": "grok_quoted_empty_data_writes_empty_string",
        "draft": {
            "extractor_type": "grok",
            "source_field": "message",
            "condition": {},
            "config": {"pattern": '"%{DATA:text}"'},
            "delete_source": False,
        },
        "event": {"message": 'say "" now'},
        "expected": {"message": 'say "" now', "text": ""},
        "status": "success",
    },
    {
        "name": "grok_nginx_dash_body_bytes_are_omitted",
        "draft": {
            "extractor_type": "grok",
            "source_field": "message",
            "condition": {},
            "config": {"pattern": "%{COMBINEDAPACHELOG}"},
            "delete_source": False,
        },
        "event": {
            "message": (
                "127.0.0.1 - frank [10/Oct/2000:13:55:36 -0700] "
                '"GET /apache_pb.gif HTTP/1.0" 200 - '
                '"http://www.example.com/start.html" '
                '"Mozilla/4.08 [en] (Win98; I ;Nav)"'
            )
        },
        "expected": {
            "message": (
                "127.0.0.1 - frank [10/Oct/2000:13:55:36 -0700] "
                '"GET /apache_pb.gif HTTP/1.0" 200 - '
                '"http://www.example.com/start.html" '
                '"Mozilla/4.08 [en] (Win98; I ;Nav)"'
            ),
            "source": {"address": "127.0.0.1"},
            "user": {"name": "frank"},
            "log_time": "10/Oct/2000:13:55:36 -0700",
            "http": {
                "request": {"method": "GET", "referrer": "http://www.example.com/start.html"},
                "version": "1.0",
                "response": {"status_code": "200"},
            },
            "url": {"original": "/apache_pb.gif"},
            "user_agent": {"original": "Mozilla/4.08 [en] (Win98; I ;Nav)"},
        },
        "status": "success",
    },
]
