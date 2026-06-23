from typing import Dict, List


def _project_one(record: Dict, projection: List[Dict]) -> Dict:
    if not projection:
        return dict(record)
    out = {}
    for item in projection:
        src = item.get("source")
        if src is None or src not in record:
            continue
        out[item.get("as") or src] = record[src]
    return out


def project(records: List[Dict], projection: List[Dict], on_multiple: str) -> Dict:
    """按基数策略把 records 投影为 enrichment[namespace] 的内容。"""
    if not records:
        return {}
    projected = [_project_one(r, projection) for r in records]
    if len(projected) == 1:
        return projected[0]
    if on_multiple == "list":
        keys = {k for p in projected for k in p}
        return {k: [p[k] for p in projected if k in p] for k in keys}
    if on_multiple == "merge":
        merged = {}
        for p in projected:
            merged.update(p)
        return merged
    # default first
    return projected[0]
