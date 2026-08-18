from collections import defaultdict


def _wadj(edges):
    w = defaultdict(dict)
    for a, b, weight in edges:
        w[a][b] = weight
        w[b][a] = weight
    return w


def test_louvain_separates_two_clusters():
    from apps.opspilot.services.wiki.graph_service import _louvain

    # 两个三角形 {1,2,3}、{4,5,6} 内部强连(权 1),仅 3-4 弱桥(权 0.1)
    wadj = _wadj([(1, 2, 1.0), (1, 3, 1.0), (2, 3, 1.0), (4, 5, 1.0), (4, 6, 1.0), (5, 6, 1.0), (3, 4, 0.1)])
    comms = _louvain({1, 2, 3, 4, 5, 6}, wadj)

    sets = sorted((frozenset(c) for c in comms), key=lambda s: min(s))
    assert len(comms) == 2
    assert sets[0] == frozenset({1, 2, 3})
    assert sets[1] == frozenset({4, 5, 6})


def test_louvain_isolated_nodes_each_own_community():
    from apps.opspilot.services.wiki.graph_service import _louvain

    comms = _louvain({1, 2, 3}, defaultdict(dict))  # 无边
    assert len(comms) == 3


def test_louvain_keeps_isolate_when_other_nodes_connect():
    """有连通分量时,孤立点仍应保留为自己的社区(聚合层不得丢弃)。"""
    from apps.opspilot.services.wiki.graph_service import _louvain

    wadj = _wadj([(1, 2, 1.0), (2, 3, 1.0), (1, 3, 1.0)])
    comms = _louvain({1, 2, 3, 99}, wadj)
    sets = {frozenset(c) for c in comms}
    assert frozenset({99}) in sets
    assert frozenset({1, 2, 3}) in sets or any({1, 2, 3} <= set(c) for c in comms)


def test_louvain_single_clique_one_community():
    from apps.opspilot.services.wiki.graph_service import _louvain

    wadj = _wadj([(1, 2, 1.0), (2, 3, 1.0), (1, 3, 1.0)])
    comms = _louvain({1, 2, 3}, wadj)
    assert len(comms) == 1 and set(comms[0]) == {1, 2, 3}
