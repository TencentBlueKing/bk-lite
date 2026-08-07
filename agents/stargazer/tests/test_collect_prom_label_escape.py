from tasks.collectors.host_collector import _escape_prometheus_label_value


def test_prometheus_label_value_escapes_reserved_characters():
    assert _escape_prometheus_label_value(
        'foo"bar\\baz\nqux'
    ) == 'foo\\"bar\\\\baz\\nqux'


def test_prometheus_label_value_keeps_plain_text():
    assert _escape_prometheus_label_value("plain-value_123") == "plain-value_123"
