import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable, Iterable

DEFAULT_VM_QUERY_MAX_WORKERS = 8
VM_QUERY_MAX_WORKERS_HARD_LIMIT = 32


def _resolve_vm_query_max_workers() -> int:
    try:
        configured = int(os.getenv("MONITOR_VM_QUERY_MAX_WORKERS", str(DEFAULT_VM_QUERY_MAX_WORKERS)))
    except (TypeError, ValueError):
        configured = DEFAULT_VM_QUERY_MAX_WORKERS
    return min(max(1, configured), VM_QUERY_MAX_WORKERS_HARD_LIMIT)


VM_QUERY_MAX_WORKERS = _resolve_vm_query_max_workers()


def run_unique_vm_queries(
    queries: Iterable[str],
    query_func: Callable[[str], Any],
) -> tuple[dict[str, Any], dict[str, Exception]]:
    """并发执行去重后的 VM 查询，并把单项失败留给调用方按原语义处理。"""
    unique_queries = list(dict.fromkeys(query for query in queries if query and query.strip()))
    if not unique_queries:
        return {}, {}

    results = {}
    errors = {}
    max_workers = min(len(unique_queries), VM_QUERY_MAX_WORKERS)
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_query = {executor.submit(query_func, query): query for query in unique_queries}
        for future in as_completed(future_to_query):
            query = future_to_query[future]
            try:
                results[query] = future.result()
            except Exception as exc:
                errors[query] = exc
    return results, errors
