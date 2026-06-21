from apps.alerts.enrichment.matcher import event_matches


def test_empty_rules_match_all():
    assert event_matches({"title": "x"}, []) is True


def test_and_within_group():
    event = {"title": "cpu high", "level": "0"}
    rules = [[{"key": "title", "operator": "contains", "value": "cpu"},
              {"key": "level", "operator": "eq", "value": "0"}]]
    assert event_matches(event, rules) is True
    rules_fail = [[{"key": "title", "operator": "contains", "value": "cpu"},
                   {"key": "level", "operator": "eq", "value": "2"}]]
    assert event_matches(event, rules_fail) is False


def test_or_across_groups():
    event = {"title": "disk full", "level": "1"}
    rules = [[{"key": "title", "operator": "contains", "value": "cpu"}],
             [{"key": "level", "operator": "eq", "value": "1"}]]
    assert event_matches(event, rules) is True


def test_missing_field_is_not_match():
    assert event_matches({"title": "x"}, [[{"key": "level", "operator": "eq", "value": "0"}]]) is False
