"""graph_service._surprise_link 单元测试。

覆盖:
- 同社区:不进入 surprise_link
- 跨社区 + 弱边(weight < min_weight):不进入
- 跨社区 + 强边 + 标题共享显著词:不进入(语义相近不算"惊奇")
- 跨社区 + 强边 + 标题不共享显著词:进入 surprise_link
- 中文 2-gram 切词:共享单字不算
- 英文按空格切:共享单词不算
- 空标题:跳过
"""

from apps.opspilot.services.wiki import graph_service


def _edge(frm, to, weight, signals=None):
    return {
        "from": frm,
        "to": to,
        "weight": weight,
        "signals": signals or {},
    }


def _page(id_, title):
    return type("P", (), {"id": id_, "title": title})()


def test_same_community_excluded():
    """同社区的强边不算 surprise。"""
    edges = [_edge(1, 2, 3.0)]
    community_of = {1: 0, 2: 0}
    by_id = {1: _page(1, "CMDB 配置"), 2: _page(2, "CMDB 平台")}
    out = graph_service._surprise_links(edges, community_of, by_id)
    assert out == []


def test_weak_edge_excluded():
    """跨社区但 weight < min_weight(默认 2.0):不进入。"""
    edges = [_edge(1, 2, 1.5)]
    community_of = {1: 0, 2: 1}
    by_id = {1: _page(1, "CMDB"), 2: _page(2, "作业平台")}
    out = graph_service._surprise_links(edges, community_of, by_id)
    assert out == []


def test_strong_edge_shared_significant_word_excluded():
    """跨社区 + 强边 + 共享显著词:不进入(surprise 强调"出乎意料")。"""
    edges = [_edge(1, 2, 3.0)]
    community_of = {1: 0, 2: 1}
    by_id = {1: _page(1, "CMDB 平台"), 2: _page(2, "CMDB 配置中心")}
    out = graph_service._surprise_links(edges, community_of, by_id)
    assert out == []


def test_strong_edge_no_shared_words_included():
    """跨社区 + 强边 + 不共享显著词:进入 surprise。"""
    edges = [_edge(1, 2, 3.0, signals={"shared_source": 2})]
    community_of = {1: 0, 2: 1}
    by_id = {1: _page(1, "CMDB"), 2: _page(2, "作业平台")}
    out = graph_service._surprise_links(edges, community_of, by_id)
    assert len(out) == 1
    assert out[0]["from"] == 1
    assert out[0]["to"] == 2
    assert out[0]["weight"] == 3.0
    assert out[0]["signals"] == {"shared_source": 2}


def test_chinese_bigram_keeps_two_char_words():
    """中文按 2-gram 切:"CMDB" 和 "作业平台" 单字不共享,应进入 surprise。"""
    edges = [_edge(1, 2, 3.0)]
    community_of = {1: 0, 2: 1}
    by_id = {1: _page(1, "CMDB"), 2: _page(2, "作业平台")}
    out = graph_service._surprise_links(edges, community_of, by_id)
    assert len(out) == 1


def test_chinese_bigram_catches_shared_substring():
    """中文标题共享 2-gram 算"显著词":不进入 surprise。"""
    edges = [_edge(1, 2, 3.0)]
    community_of = {1: 0, 2: 1}
    by_id = {1: _page(1, "蓝鲸 CMDB"), 2: _page(2, "蓝鲸 SaaS")}
    out = graph_service._surprise_links(edges, community_of, by_id)
    # 共享"蓝鲸"
    assert out == []


def test_english_shared_word_excluded():
    """英文标题共享单词:不进入 surprise。"""
    edges = [_edge(1, 2, 3.0)]
    community_of = {1: 0, 2: 1}
    by_id = {1: _page(1, "CMDB platform"), 2: _page(2, "CMDB service")}
    out = graph_service._surprise_links(edges, community_of, by_id)
    # 共享 "cmdb"
    assert out == []


def test_empty_title_handled():
    """空标题不参与计算。"""
    edges = [_edge(1, 2, 3.0)]
    community_of = {1: 0, 2: 1}
    by_id = {1: _page(1, ""), 2: _page(2, "作业平台")}
    out = graph_service._surprise_links(edges, community_of, by_id)
    assert out == []


def test_missing_page_skipped():
    """page 缺失:跳过。"""
    edges = [_edge(1, 2, 3.0)]
    community_of = {1: 0, 2: 1}
    by_id = {1: _page(1, "CMDB")}  # 2 缺失
    out = graph_service._surprise_links(edges, community_of, by_id)
    assert out == []


def test_top_n_sorted_by_weight_desc():
    """surprise_links 按 weight 降序排序,取 limit。"""
    edges = [
        _edge(1, 2, 1.5),
        _edge(3, 4, 5.0),
        _edge(5, 6, 3.0),
    ]
    community_of = {1: 0, 2: 1, 3: 0, 4: 1, 5: 0, 6: 1}
    by_id = {
        1: _page(1, "CMDB"),
        2: _page(2, "作业平台"),
        3: _page(3, "GSE"),
        4: _page(4, "管控平台"),
        5: _page(5, "ESB"),
        6: _page(6, "企业服务总线"),
    }
    out = graph_service._surprise_links(edges, community_of, by_id, min_weight=1.0)
    # 1.5 < 2.0(默认) 但这里我设了 min_weight=1.0,所以 3 条都进;按 weight 排序
    assert [e["weight"] for e in out] == sorted((e["weight"] for e in out), reverse=True)
