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


def test_regex_operator_matches():
    # 前端「正则」操作符 re 必须被引擎支持，否则规则会静默永不命中
    event = {"resource_name": "10.10.69.248-switch"}
    assert event_matches(event, [[{"key": "resource_name", "operator": "re", "value": r"^10\.10\..*-switch$"}]]) is True
    assert event_matches(event, [[{"key": "resource_name", "operator": "re", "value": r"^192\."}]]) is False


def test_invalid_regex_does_not_raise():
    # 非法正则不得抛异常，按不匹配处理
    event = {"title": "x"}
    assert event_matches(event, [[{"key": "title", "operator": "re", "value": "("}]]) is False
