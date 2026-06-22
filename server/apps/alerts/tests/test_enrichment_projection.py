from apps.alerts.enrichment.projection import project


def test_project_selects_and_renames():
    records = [{"responsible_person": "alice", "biz": "pay", "noise": "x"}]
    proj = [{"source": "responsible_person", "as": "owner"}, {"source": "biz"}]
    assert project(records, proj, "first") == {"owner": "alice", "biz": "pay"}


def test_empty_projection_takes_all_fields():
    records = [{"a": 1, "b": 2}]
    assert project(records, [], "first") == {"a": 1, "b": 2}


def test_zero_records_returns_empty():
    assert project([], [{"source": "a"}], "first") == {}


def test_on_multiple_first():
    records = [{"a": 1}, {"a": 2}]
    assert project(records, [{"source": "a"}], "first") == {"a": 1}


def test_on_multiple_list():
    records = [{"a": 1}, {"a": 2}]
    assert project(records, [{"source": "a"}], "list") == {"a": [1, 2]}


def test_on_multiple_merge_last_wins():
    records = [{"a": 1, "b": 1}, {"a": 2}]
    assert project(records, [], "merge") == {"a": 2, "b": 1}
