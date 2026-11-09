from apps.itsm.flowable.expressions import to_juel


def test_compare_and_group():
    text = to_juel(
        {"logic": "and", "items": [{"field": "form.amount", "op": ">", "value": 1000}, {"field": "form.priority", "op": "=", "value": "P1"}]}
    )
    assert text == "${(form_amount > 1000 && form_priority == 'P1')}"


def test_empty_and_in():
    assert "empty form_title" in to_juel({"field": "form.title", "op": "is_empty"})
    assert "form_priority == 'P1'" in to_juel({"field": "form.priority", "op": "in", "value": ["P1", "P2"]})
