"""SearchService 剩余查询编排：hits 无分组、top_stats 空总数、tail 响应头。"""
from unittest.mock import MagicMock

from django.http import StreamingHttpResponse

from apps.log.services.search import SearchService


def test_search_hits_without_group_info_returns_raw(mocker):
    mocker.patch(
        "apps.log.services.search.LogGroupQueryBuilder.build_query_with_groups",
        return_value=("FQ", []),
    )
    vm = mocker.patch("apps.log.services.search.VictoriaMetricsAPI").return_value
    vm.hits.return_value = {"hits": [{"count": 1}]}
    out = SearchService.search_hits("q", "s", "e", "host")
    assert out == {"hits": [{"count": 1}]}
    assert "_log_group_info" not in out


def test_search_logs_applies_default_window(mocker):
    mocker.patch(
        "apps.log.services.search.LogGroupQueryBuilder.build_query_with_groups",
        return_value=("FQ", []),
    )
    vm = mocker.patch("apps.log.services.search.VictoriaMetricsAPI").return_value
    vm.query.return_value = {"data": []}
    SearchService.search_logs("", "", "", limit=4)
    start, end = vm.query.call_args.args[1], vm.query.call_args.args[2]
    assert start.endswith("Z") and end.endswith("Z")
    assert start < end


def test_top_stats_empty_total_response(mocker):
    mocker.patch(
        "apps.log.services.search.LogGroupQueryBuilder.build_query_with_groups",
        return_value=("FQ", []),
    )
    vm = mocker.patch("apps.log.services.search.VictoriaMetricsAPI").return_value
    vm.query.side_effect = [None, []]
    out = SearchService.top_stats("q", "s", "e", "host")
    assert out == {"attr": "host", "top_num": 5, "total": 0, "items": []}


def test_tail_sets_sse_headers(mocker):
    mocker.patch(
        "apps.log.services.search.LogGroupQueryBuilder.build_query_with_groups",
        return_value=("error", []),
    )
    mocker.patch("apps.log.services.search.VictoriaMetricsAPI", return_value=MagicMock())
    response = SearchService.tail("error")
    assert isinstance(response, StreamingHttpResponse)
    assert response["Content-Type"] == "text/event-stream"
    assert response["Cache-Control"] == "no-cache, no-store, must-revalidate"
    assert response["X-Accel-Buffering"] == "no"
