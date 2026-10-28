"""OpsPilot 调用 MLOps 时序预测。一次工具调用里按序列并发，不让模型抄点。"""

import json
import time
from concurrent.futures import ThreadPoolExecutor, wait
from typing import Annotated, Any, Optional

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from pydantic import Field

from apps.core.logger import opspilot_logger as logger
from apps.opspilot.metis.llm.tools.mlops.monitor_store import (
    cached_monitor_metrics,
    execution_id_from_config,
    latest_monitor_metric_query,
    record_monitor_metric_query,
)
from apps.opspilot.metis.llm.tools.mlops.reshape import DEFAULT_TIMEZONE, prepare_series, summarize_prediction
from apps.opspilot.metis.llm.tools.mlops.series import extract_monitor_series, select_series
from apps.opspilot.metis.llm.tools.monitor.utils import call_monitor_rpc, format_monitor_caller_identity_required_error, resolve_monitor_user_info
from apps.rpc.mlops import MLOps

MAX_SERIES = 100
CONCURRENCY = 5
WALL_SECONDS = 240
PREDICT_RPC_TIMEOUT_SECONDS = 140
DECLARED_LOOKBACK_MS = 14 * 24 * 60 * 60 * 1000
DECLARED_PARAMS_ERROR = (
    "请同时传入 monitor_obj_id、metric、instance_ids，并与 monitor_query_metric_data 使用同一组参数。"
    "instance_ids 必须原样复制 monitor_list_object_instances 返回的 instance_id，禁止改成 IP 或主机名。"
)

_TOOL_DESCRIPTION = (
    "用已绑定的 MLOps 时序预测服务预测未来。不要自己心算外推。"
    "view=summary 用于比较多条序列，回答哪台最危险、峰值何时出现，只返回每条的最大值、最终值和到达时间；"
    "view=trend 只允许 1 条序列，这时才列出预测点，同时返回摘要。"
    "监控路径必须同时传入 monitor_obj_id、metric、instance_ids，三者都原样复制本轮 monitor_query_metric_data 的同名参数。"
    "instance_ids 的值来自 monitor_list_object_instances 的 instance_id，禁止改成 IP 或主机名，也不要把点写入 data。"
    "用户贴出的单条序列传 data。metric 和 data 只能有一个。"
    "horizon_days 是用户要看的未来天数。steps 是未来点数不是天数，等于跨度除以输入点间隔。"
    "向用户表述预测跨度时，用返回的频率乘以 steps 换算成真实时间。"
    "threshold 只在用户明确说出阈值时传入，不要默认 100。"
    "serving_id 在绑定了多个预测服务时必须从工具说明里的列表选择；只绑定一个时不用传。"
)


def run_bounded(items: list, worker, concurrency: int = CONCURRENCY, wall_seconds: float = WALL_SECONDS) -> list:
    if not items:
        return []
    executor = ThreadPoolExecutor(max_workers=max(1, concurrency))
    futures = {executor.submit(worker, item): item for item in items}
    done, pending = wait(futures, timeout=wall_seconds)
    results = []
    for future in done:
        item = futures[future]
        try:
            results.append(future.result())
        except Exception as exc:
            results.append(_failed_row(item, f"预测失败: {type(exc).__name__}", "predict", type(exc).__name__))
    for future in pending:
        future.cancel()
        results.append(_failed_row(futures[future], "预测超时", "predict", "timeout"))
    executor.shutdown(wait=False, cancel_futures=True)
    return results


def mlops_predict_timeseries_impl(
    view: str,
    horizon_days: float,
    serving_id: Optional[int] = None,
    metric: Optional[str] = None,
    instance_ids: Optional[list] = None,
    data: Optional[list] = None,
    threshold: Optional[float] = None,
    monitor_obj_id: Optional[str] = None,
    config: RunnableConfig = None,
    predict_caller=None,
    wall_seconds: float = WALL_SECONDS,
) -> dict:
    started = time.monotonic()
    configurable = _configurable(config)
    metric, data, cache_error = _resolve_monitor_source(configurable, metric, data)
    if cache_error:
        return {"success": False, "error": cache_error}
    source_error = _validate_source(metric, data)
    if source_error:
        return {"success": False, "error": source_error}
    if view not in ("summary", "trend"):
        return {"success": False, "error": "view 只能是 summary 或 trend"}
    try:
        prepared_horizon = float(horizon_days)
    except (TypeError, ValueError):
        return {"success": False, "error": "horizon_days 必须是正数"}

    try:
        identity = resolve_monitor_user_info(config)
    except ValueError as exc:
        return {"success": False, "error": str(exc) or format_monitor_caller_identity_required_error(config)}

    serving, serving_error = _resolve_serving(configurable, serving_id)
    if serving_error:
        return {"success": False, "error": serving_error}

    series, missing, none_matched = _load_series(config, metric, instance_ids, data)
    if none_matched and data is None:
        declared = _normalize_ids(instance_ids)
        if str(metric or "").strip() and str(monitor_obj_id or "").strip() and declared:
            queried, query_error = _query_declared_series(config, str(monitor_obj_id), str(metric), declared)
            if query_error:
                return {"success": False, "error": query_error}
            series = extract_monitor_series(queried)
            missing = []
            none_matched = not series
    if none_matched:
        if data is None and not (str(monitor_obj_id or "").strip() and _normalize_ids(instance_ids)):
            return {"success": False, "error": DECLARED_PARAMS_ERROR}
        return {"success": False, "error": "监控查询没有返回序列。请确认 instance_ids 原样复制自 monitor_list_object_instances 的 instance_id。"}
    if view == "trend" and len(series) != 1:
        return {"success": False, "error": "view=trend 只允许 1 条序列，请先用 instance_ids 收成一台"}
    if len(series) > MAX_SERIES:
        return {"success": False, "error": f"序列超过 {MAX_SERIES} 条，请先用监控筛出要预测的实例"}

    timezone_name = str(configurable.get("timezone") or DEFAULT_TIMEZONE)
    jobs = []
    early_errors = []
    frequency = ""
    steps = 0
    for item in series:
        prepared = prepare_series(item["points"], prepared_horizon)
        frequency = prepared["frequency"]
        steps = prepared["steps"]
        if not prepared["ok"]:
            early_errors.append(_failed_row(item, prepared["error"], "prepare", "series_error"))
            continue
        jobs.append({**item, "prepared": prepared})

    actor_context = {
        "username": identity["user"],
        "domain": identity["domain"],
        "team_id": identity["team"],
        "locale": configurable.get("locale") or "zh-Hans",
    }
    caller = predict_caller or _default_predict

    def _worker(job):
        prepared = job["prepared"]
        response = caller(serving["id"], prepared["data"], prepared["steps"], actor_context)
        return _row_from_response(job, prepared, response, view, threshold, timezone_name)

    predicted = run_bounded(jobs, _worker, wall_seconds=wall_seconds)
    results = early_errors + [_missing_row(name) for name in missing] + predicted
    results.sort(
        key=lambda item: (
            (item.get("summary") or {}).get("max_value") is not None,
            (item.get("summary") or {}).get("max_value") or 0,
        ),
        reverse=True,
    )
    succeeded = sum(1 for item in results if not item.get("error"))
    failed = len(results) - succeeded
    logger.info(
        "event=mlops_timeseries_predict_finished serving_id=%s series=%s succeeded=%s failed=%s duration_ms=%s",
        serving["id"],
        len(results),
        succeeded,
        failed,
        int((time.monotonic() - started) * 1000),
    )
    payload = {
        "success": succeeded > 0,
        "serving": serving,
        "frequency": frequency,
        "steps": steps,
        "view": view,
        "results": results,
    }
    if succeeded == 0:
        payload["error"] = "全部序列预测失败"
    return payload


@tool(description=_TOOL_DESCRIPTION)
def mlops_predict_timeseries(
    view: Annotated[str, Field(description="summary 比较多条序列；trend 只看 1 条序列")],
    horizon_days: Annotated[float, Field(description="用户要看的未来天数")],
    metric: Annotated[Optional[str], Field(description="原样复制 monitor_query_metric_data 的 metric")] = None,
    instance_ids: Annotated[
        Optional[list],
        Field(description="原样复制 monitor_query_metric_data 的 instance_ids，值是 monitor_list_object_instances 的 instance_id，禁止改成 IP"),
    ] = None,
    monitor_obj_id: Annotated[Optional[str], Field(description="原样复制 monitor_query_metric_data 的 monitor_obj_id")] = None,
    serving_id: Annotated[Optional[int], Field(description="绑定多个预测服务时必填，值来自工具说明中的 id")] = None,
    data: Annotated[Optional[list], Field(description="仅用户自己贴出单条序列时传入；本轮已查监控时不要传")] = None,
    threshold: Annotated[Optional[float], Field(description="仅用户明确说出阈值时传入")] = None,
    config: RunnableConfig = None,
) -> dict:
    return mlops_predict_timeseries_impl(
        view,
        horizon_days,
        serving_id=serving_id,
        metric=metric,
        instance_ids=instance_ids,
        data=data,
        threshold=threshold,
        monitor_obj_id=monitor_obj_id,
        config=config,
    )


def _default_predict(serving_id: int, data: list, steps: int, actor_context: dict) -> dict:
    client = MLOps()
    return client.predict_timeseries_serving(
        serving_id=serving_id,
        data=data,
        steps=steps,
        actor_context=actor_context,
        _timeout=PREDICT_RPC_TIMEOUT_SECONDS,
    )


def _configurable(config: Optional[RunnableConfig]) -> dict:
    if not isinstance(config, dict):
        return {}
    configurable = config.get("configurable")
    return configurable if isinstance(configurable, dict) else {}


def _resolve_monitor_source(configurable: dict, metric: Optional[str], data: Optional[list]) -> tuple[Optional[str], Optional[list], str]:
    """本轮已有监控结果时，不采用模型传入的点，避免使用被截断的序列。"""
    if data is None:
        return metric, data, ""
    execution_id = execution_id_from_config({"configurable": configurable})
    cached = cached_monitor_metrics(execution_id)
    if not cached:
        return metric, data, ""
    chosen = str(metric or "").strip()
    if chosen and chosen not in cached:
        listed = "、".join(cached)
        return None, None, f"本轮已有监控结果，不要把点放入 data。请改传其中的 metric：{listed}"
    if not chosen and len(cached) == 1:
        chosen = cached[0]
    if not chosen:
        listed = "、".join(cached)
        return None, None, f"本轮已有监控结果，不要把点放入 data。请改传其中的 metric：{listed}"
    logger.debug(
        "event=mlops_timeseries_predict_ignored_pasted_data metric=%s failed_stage=source error_type=cached_series_preferred",
        chosen,
    )
    return chosen, None, ""


def _validate_source(metric: Optional[str], data: Optional[list]) -> str:
    has_metric = bool(str(metric or "").strip())
    has_data = data is not None
    if has_metric and has_data:
        return "metric 和 data 只能传一个"
    if not has_metric and not has_data:
        return "请传 metric 引用本轮监控结果，或传 data"
    return ""


def _parse_serving_ids(raw: Any) -> list[int]:
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return []
        try:
            raw = json.loads(text)
        except json.JSONDecodeError:
            raw = [part.strip() for part in text.split(",") if part.strip()]
    if isinstance(raw, int) and not isinstance(raw, bool):
        raw = [raw]
    if not isinstance(raw, list):
        return []
    parsed = []
    for item in raw:
        try:
            parsed.append(int(item))
        except (TypeError, ValueError):
            continue
    return parsed


def _resolve_serving(configurable: dict, serving_id: Optional[int]) -> tuple[Optional[dict], str]:
    bound = _parse_serving_ids(configurable.get("serving_ids"))
    if not bound:
        return None, "智能体还没有绑定时序预测服务"
    names = _serving_names(bound)
    if len(bound) == 1:
        chosen = bound[0]
    else:
        try:
            chosen = int(serving_id)
        except (TypeError, ValueError):
            chosen = None
        if chosen not in bound:
            options = "、".join(f"{item}:{names.get(item, '')}" for item in bound)
            return None, f"serving_id 必须是已绑定的服务之一：{options}"
    return {"id": chosen, "name": names.get(chosen, "")}, ""


def get_mlops_serving_prompt(tool_kwargs: Optional[dict]) -> str:
    bound = _parse_serving_ids((tool_kwargs or {}).get("serving_ids"))
    if not bound:
        return "尚未绑定时序预测服务。配置智能体时必须选择一个服务。"
    names = _serving_names(bound)
    listed = "、".join(f"{item}:{names.get(item, '')}" for item in bound)
    if len(bound) == 1:
        return f"已绑定的时序预测服务（id:名称）：{listed}。当前只有一个，调用时不用传 serving_id。"
    return f"已绑定的时序预测服务（id:名称）：{listed}。调用时必须传列表中的 serving_id。"


def _serving_names(serving_ids: list[int]) -> dict[int, str]:
    from apps.mlops.models.timeseries_predict import TimeSeriesPredictServing

    rows = TimeSeriesPredictServing.objects.filter(id__in=serving_ids).values("id", "name")
    return {row["id"]: row["name"] for row in rows}


def _normalize_ids(instance_ids: Optional[list]) -> list[str]:
    if not isinstance(instance_ids, list):
        return []
    normalized = []
    for item in instance_ids:
        text = str(item or "").strip()
        if text and text not in normalized:
            normalized.append(text)
    return normalized


def _query_declared_series(config: Optional[RunnableConfig], monitor_obj_id: str, metric: str, instance_ids: list[str]):
    now_ms = int(time.time() * 1000)
    result = call_monitor_rpc(
        "query_monitor_data_by_metric",
        config,
        query_data={
            "monitor_obj_id": monitor_obj_id,
            "metric": metric,
            "start": now_ms - DECLARED_LOOKBACK_MS,
            "end": now_ms,
            "step": "5m",
            "instance_ids": list(instance_ids),
            "dimensions": {},
        },
    )
    if not isinstance(result, dict) or result.get("success") is False:
        message = str(result.get("error") or "") if isinstance(result, dict) else ""
        return None, message or "监控查询失败"
    record_monitor_metric_query(config, metric, instance_ids, result, monitor_obj_id=monitor_obj_id)
    return result, ""


def _load_series(config: Optional[RunnableConfig], metric: Optional[str], instance_ids: Optional[list], data: Optional[list]):
    if data is not None:
        return [{"instance_id": None, "instance": "", "labels": {}, "points": list(data)}], [], False
    entry = latest_monitor_metric_query(execution_id_from_config(config), str(metric or ""))
    if entry is None:
        return [], [], True
    series = extract_monitor_series(entry.get("payload"))
    if not series:
        return [], [], True
    requested = _normalize_ids(instance_ids)
    queried = _normalize_ids(entry.get("instance_ids"))
    if requested and requested != queried:
        selected, missing = select_series(series, requested)
        if selected:
            return selected, missing, False
    return series, [], False


def _row_from_response(job, prepared, response, view, threshold, timezone_name) -> dict:
    if not isinstance(response, dict) or response.get("result") is False:
        message = ""
        if isinstance(response, dict):
            message = str(response.get("message") or "")
        return _failed_row(job, message or "预测服务拒绝了这次请求", "predict", "upstream_rejected")
    body = response.get("data") if isinstance(response.get("data"), dict) else response
    summary = summarize_prediction(body.get("prediction") or [], prepared["last_timestamp"], timezone_name)
    if summary.get("error"):
        return _failed_row(job, summary["error"], "summarize", "series_error")
    row = {
        "instance_id": job.get("instance_id"),
        "summary": {key: summary[key] for key in ("max_value", "max_time", "max_offset", "final_value", "final_time", "final_offset")},
        "error": None,
    }
    if threshold is not None:
        try:
            row["over_threshold"] = summary["max_value"] >= float(threshold)
        except (TypeError, ValueError):
            row["over_threshold"] = False
    if view == "trend":
        row["trend"] = summary["trend"]
    return row


def _failed_row(item: dict, message: str, failed_stage: str, error_type: str) -> dict:
    logger.debug(
        "event=mlops_timeseries_predict_series_failed instance_id=%s failed_stage=%s error_type=%s",
        item.get("instance_id"),
        failed_stage,
        error_type,
    )
    return {"instance_id": item.get("instance_id"), "summary": None, "error": message}


def _missing_row(instance_id: str) -> dict:
    return {"instance_id": instance_id, "summary": None, "error": "监控结果里没有这个实例"}
