from types import SimpleNamespace

from apps.alerts.notification_templates.events import event_row


class _EventQuery:
    def __init__(self, rows):
        self.rows = rows
        self.fetches = 0

    def select_related(self, *_args):
        return self

    def defer(self, *_args):
        return self

    def order_by(self, *_args):
        self.fetches += 1
        return self

    def __getitem__(self, _item):
        return self.rows

    def first(self):
        self.fetches += 1
        return self.rows[0] if self.rows else None


class _Events:
    def __init__(self, rows):
        self.rows = rows
        self.counts = 0
        self.query = _EventQuery(rows)

    def count(self):
        self.counts += 1
        return 47

    def select_related(self, *args):
        return self.query.select_related(*args)


def _alert(events):
    alert = SimpleNamespace(pk=9, level="1", title="连接数过高", team=[1], events=events)
    return alert


def test_event_row_drops_raw_payload(monkeypatch):
    monkeypatch.setattr(
        "apps.alerts.notification_templates.binding._event_level_names",
        lambda: {"1": "严重"},
    )
    event = SimpleNamespace(
        level="1",
        title="cpu",
        raw_data={"token": "secret-token"},
        tags={"alert": "ConnHigh"},
        labels={},
        enrichment={},
        source=SimpleNamespace(name="Prometheus"),
    )

    row = event_row(event, {"1": "严重"})

    assert row["level"] == "严重"
    assert row["source_name"] == "Prometheus"
    assert row["tags"]["alert"] == "ConnHigh"
    assert "raw_data" not in row
    assert "secret-token" not in str(row)


def test_unused_template_does_not_touch_events(monkeypatch):
    from apps.alerts.notification_templates.binding import load_event_context

    events = _Events([])
    monkeypatch.setattr("apps.alerts.notification_templates.binding._event_level_names", lambda: {})

    context = load_event_context(_alert(events), ("<p>{{ alert.title }}</p>",))

    assert context["rows_by_order"] == {}
    assert events.counts == 0
    assert events.query.fetches == 0


def test_shared_state_loads_each_order_once(monkeypatch):
    from apps.alerts.notification_templates.binding import load_event_context

    event = SimpleNamespace(
        level="1",
        title="cpu",
        resource_name="host-0",
        tags={"alert": "ConnHigh"},
        labels={},
        enrichment={},
        source=SimpleNamespace(name="Prometheus"),
    )
    events = _Events([event])
    monkeypatch.setattr("apps.alerts.notification_templates.binding._event_level_names", lambda: {"1": "严重"})
    sources = ("{{ events.count }}{{@ events columns=resource_name, tags.alert @}}",)
    state = {}

    first = load_event_context(_alert(events), sources, state)
    second = load_event_context(_alert(events), sources, state)

    assert events.counts == 1
    assert events.query.fetches == 1
    assert first["count"] == 47
    assert first["rows_by_order"]["-start_time"][0]["resource_name"] == "host-0"
    assert second["rows_by_order"]["-start_time"][0]["level"] == "严重"
    assert "secret" not in str(first)


def test_dispatcher_reuses_one_event_state_across_channels(monkeypatch):
    from apps.alerts.common.notify.dispatcher import build_channel_params

    states = []

    def load_events(alert, sources, state=None):
        states.append(state)
        state["hits"] = state.get("hits", 0) + 1
        return {"count": state["hits"], "latest": {}, "first": {}, "rows_by_order": {}}

    def render(*_args, **kwargs):
        kwargs["event_context_loader"](SimpleNamespace(pk=1), ("{{ events.count }}",))
        return SimpleNamespace(title="t", content="body", template_id=3, revision=1, missing_fields=[])

    monkeypatch.setattr("apps.alerts.common.notify.base.NotifyParamsFormat.get_user_timezone", lambda self: "Asia/Shanghai")
    monkeypatch.setattr("apps.alerts.common.notify.dispatcher.load_event_context", load_events)
    monkeypatch.setattr("apps.alerts.common.notify.dispatcher.render_bound_template", render)
    channels = [
        {"id": 1, "channel_type": "email", "notification_templates": {"assignment": 3}},
        {"id": 2, "channel_type": "enterprise_wechat_bot", "notification_templates": {"assignment": 3}},
    ]

    build_channel_params(["admin"], channels, [SimpleNamespace(pk=1, team=[1])], "ALERT-1", scene="assignment")

    assert len(states) == 2
    assert states[0] is states[1]
    assert states[0]["hits"] == 2
