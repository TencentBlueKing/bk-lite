from apps.apm.services.trace_access import collect_visible_page


def test_collect_visible_page_filters_before_advertising_cursor():
    pages = {
        None: (("hidden", "visible-a", "hidden-b"), "cursor-1"),
        "cursor-1": (("visible-b",), None),
    }

    items, next_cursor = collect_visible_page(
        fetch_page=lambda cursor: pages[cursor],
        filter_items=lambda rows: tuple(item for item in rows if item.startswith("visible")),
        cursor=None,
        limit=20,
        encode_cursor=lambda item: f"from:{item}",
    )

    assert items == ("visible-a", "visible-b")
    assert next_cursor is None


def test_collect_visible_page_encodes_cursor_from_last_visible_when_page_overflows():
    items, next_cursor = collect_visible_page(
        fetch_page=lambda cursor: (("hidden", "a", "b", "c"), "store-next") if cursor is None else ((), None),
        filter_items=lambda rows: tuple(item for item in rows if item != "hidden"),
        cursor=None,
        limit=2,
        encode_cursor=lambda item: f"from:{item}",
    )

    assert items == ("a", "b")
    assert next_cursor == "from:b"
