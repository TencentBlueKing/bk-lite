"""OpsPilot 作业工具的会话侧流程。

提交前先记下作业号。脚本输出写入展示块，返回给模型的只有作业号和终态。
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

from django.core.files.base import ContentFile
from django.db import close_old_connections
from django.utils import timezone

from apps.core.logger import opspilot_logger as logger
from apps.opspilot.metis.llm.tools.rpc_identity import configurable_from_config, resolve_rpc_user_info
from apps.opspilot.metis.llm.tools.search_terms import user_message_from_config
from apps.opspilot.models import ChatAttachment, SkillConversation, SkillConversationMessage
from apps.opspilot.services.chat_attachment_service import DISTRIBUTE_STAGE_REASON_PREFIX
from apps.rpc.job_mgmt import JobMgmt
from apps.rpc.job_opspilot import (
    ACTION_DESCRIBE_SCRIPT,
    ACTION_DISTRIBUTE,
    ACTION_EXECUTE,
    ACTION_LIST_PLAYBOOK_SCRIPTS,
    ACTION_LIST_SCRIPTS,
    ACTION_LIST_TARGETS,
    ACTION_QUERY,
    ACTION_SEARCH_TARGETS,
    new_job_file_key,
    sign_opspilot_job_request,
)

STATUS_PENDING = "pending"
STATUS_SUCCESS = "success"
STATUS_FAILED = "failed"
STATUS_TIMEOUT = "timeout"
STATUS_CANCELLED = "cancelled"
TERMINAL_STATUSES = {STATUS_SUCCESS, STATUS_FAILED, STATUS_TIMEOUT, STATUS_CANCELLED}
RERUN_STATUSES = {STATUS_FAILED, STATUS_TIMEOUT, STATUS_CANCELLED}
KIND_SCRIPT = "script"
KIND_FILE = "file"
JOB_RECORD_NAME = "job_record"
JOB_OUTPUT_NAME = "job_script_output"
JOB_RECORD_MARK = '"name": "job_record"'
# 同一次工具返回后，流式线程从这里取展示块。调试会话没有 SkillConversation 时库里没有这份记录。
_PENDING_DISPLAYS: dict[int, dict] = {}
STAGED_FILE_DAYS = 7
WATCH_HOURS = 24
DEFAULT_WATCH_MINUTES = 60
CUSTOM_TIMEOUT_SECONDS = 600
_TYPE_PATTERNS = {
    "shell": re.compile(r"(?i)(?<![A-Za-z0-9])(?:shell|bash|sh)(?![A-Za-z0-9])"),
    "python": re.compile(r"(?i)(?<![A-Za-z0-9])python(?![A-Za-z0-9])"),
    "powershell": re.compile(r"(?i)(?<![A-Za-z0-9])(?:powershell|pwsh|ps)(?![A-Za-z0-9])"),
    "bat": re.compile(r"(?i)(?<![A-Za-z0-9])(?:bat|batch|cmd)(?![A-Za-z0-9])"),
}


class JobToolError(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def distribute_owner_key(username: str, domain: str) -> str:
    """暂存文件和工具查询使用同一把钥匙：调用身份的用户名和域。"""

    return f"{username}@{domain}"


def _owner_key(user_info) -> str:
    return distribute_owner_key(user_info["user"], user_info["domain"])


def session_context(config):
    """没有调用身份时拒绝。组织固定为当前组织，不展开子组织。"""

    try:
        identity = resolve_rpc_user_info(config, "作业管理")
    except ValueError as exc:
        raise JobToolError(str(exc)) from exc
    user_info = {
        "user": identity["user"],
        "domain": identity["domain"],
        "team": identity["team"],
        "include_children": False,
    }
    configurable = configurable_from_config(config)
    session_key = str(configurable.get("skill_session_id") or configurable.get("session_id") or configurable.get("conversation_key") or "").strip()
    if not session_key:
        raise JobToolError("当前会话缺失，不能提交作业")
    return user_info, session_key, configurable


def _conversation_for_key(session_key: str):
    key = str(session_key or "").strip()
    candidates = [key] if key else []
    if key.startswith("skill:") and key[6:]:
        candidates.append(key[6:])
    if not candidates:
        return None
    found = {row.session_id: row for row in SkillConversation.objects.filter(session_id__in=candidates)}
    for candidate in candidates:
        row = found.get(candidate)
        if row is not None:
            return row
    return None


def current_user_text(config, session_key: str) -> str:
    text = user_message_from_config(config)
    if isinstance(text, str) and text.strip():
        return text
    conversation = _conversation_for_key(session_key)
    if conversation is None:
        return ""
    message = conversation.messages.filter(role=SkillConversationMessage.ROLE_USER).order_by("-id").first()
    return message.content if message else ""


def _raw_config_user_text(config) -> str:
    configurable = configurable_from_config(config)
    graph_request = configurable.get("graph_request")
    candidates = [
        getattr(graph_request, "graph_user_message", "") if graph_request is not None else "",
        getattr(graph_request, "user_message", "") if graph_request is not None else "",
        configurable.get("graph_user_message") or "",
        configurable.get("user_message") or "",
    ]
    for message in candidates:
        if isinstance(message, str) and message.strip():
            return message
    return ""


def user_statement_texts(config, session_key: str) -> list[str]:
    """本会话里用户说过的话。当前这句放在最前，随后是更早的用户消息。"""

    texts = []
    seen = set()

    def add(value):
        if not isinstance(value, str):
            return
        text = value.strip()
        if not text or text in seen:
            return
        seen.add(text)
        texts.append(text)

    add(_raw_config_user_text(config))
    for content in _chat_history_user_texts(config):
        add(content)
    conversation = _conversation_for_key(session_key)
    if conversation is not None:
        earlier = conversation.messages.filter(role=SkillConversationMessage.ROLE_USER).order_by("-id").values_list("content", flat=True)[:20]
        for content in earlier:
            add(content)
    if not texts:
        add(current_user_text(config, session_key))
    return texts


def _rpc(action, user_info, body, files=None, timeout=30):
    """通过作业 RPC 客户端调用。默认走 NATS，不在这里导入作业应用。"""

    payload = {
        "action": action,
        "_internal_auth": sign_opspilot_job_request(action, user_info),
        "user_info": user_info,
        "body": body,
    }
    if files is not None:
        payload["files"] = files

    def _invoke():
        return JobMgmt().job_opspilot_action(payload, timeout=timeout)

    try:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            result = _invoke()
        else:
            # RpcClient.run 内部是 asyncio.run。对话节点已经在事件循环里，直接调用会失败。
            with ThreadPoolExecutor(max_workers=1) as pool:
                result = pool.submit(_invoke).result()
    except Exception as exc:
        logger.warning(
            "event=opspilot_job_rpc_failed action=%s failed_stage=rpc error_type=%s",
            action,
            type(exc).__name__,
        )
        return {"result": False, "message": "作业平台暂时不可用"}
    if not isinstance(result, dict):
        logger.warning(
            "event=opspilot_job_rpc_failed action=%s failed_stage=rpc error_type=invalid_response",
            action,
        )
        return {"result": False, "message": "作业平台暂时不可用"}
    return result


def _call(action, user_info, body):
    return _rpc(action, user_info, body)


def _fingerprint(kind, body, file_ids=None) -> str:
    material = {
        "kind": kind,
        "script_id": body.get("script_id"),
        "script_type": body.get("script_type"),
        "script_content": body.get("script_content"),
        "target_source": body.get("target_source"),
        "target_ids": body.get("target_ids"),
        "params": body.get("params"),
        "target_path": body.get("target_path"),
        "overwrite_strategy": body.get("overwrite_strategy"),
        "file_ids": file_ids,
    }
    raw = json.dumps(material, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _iso(value) -> str:
    return value.isoformat()


def _parse_iso(value):
    parsed = datetime.fromisoformat(str(value))
    if timezone.is_naive(parsed):
        return timezone.make_aware(parsed, timezone.get_current_timezone())
    return parsed


def _parse_note_content(content: str):
    try:
        events = json.loads(content)
    except json.JSONDecodeError:
        return None
    if not isinstance(events, list):
        return None
    record = None
    output = None
    for event in events:
        if not isinstance(event, dict) or event.get("type") != "CUSTOM":
            continue
        if event.get("name") == JOB_RECORD_NAME and isinstance(event.get("value"), dict):
            record = event["value"]
        elif event.get("name") == JOB_OUTPUT_NAME and isinstance(event.get("value"), dict):
            output = event["value"]
    if record is None:
        return None
    return record, output


def _visible_text(content: str) -> str:
    parsed = _parse_note_content(content)
    if parsed is None:
        return ""
    try:
        events = json.loads(content)
    except json.JSONDecodeError:
        return ""
    parts = []
    for event in events:
        if isinstance(event, dict) and event.get("type") == "TEXT_MESSAGE_CONTENT":
            parts.append(str(event.get("delta") or ""))
    return "".join(parts).strip()


class _JobNote:
    """会话消息里的作业记录。没有单独的表。"""

    def __init__(self, message, record, output=None):
        self.message = message
        self.record = record
        self.output = output

    @property
    def task_id(self):
        return self.record["task_id"]

    @property
    def kind(self):
        return self.record["kind"]

    @property
    def status(self):
        return self.record["status"]

    @status.setter
    def status(self, value):
        self.record["status"] = value

    @property
    def submitted_at(self):
        return _parse_iso(self.record["submitted_at"])

    @property
    def session_key(self):
        return self.record["session_key"]

    def save(self, visible=None):
        if self.message is None:
            return
        if visible is None:
            visible = _visible_text(self.message.content)
        events = [{"type": "CUSTOM", "name": JOB_RECORD_NAME, "value": self.record}]
        if self.output is not None:
            events.append({"type": "CUSTOM", "name": JOB_OUTPUT_NAME, "value": self.output})
        events.append({"type": "TEXT_MESSAGE_CONTENT", "delta": visible})
        self.message.content = json.dumps(events, ensure_ascii=False)
        self.message.save(update_fields=["content"])


def _note_matches(record, user_info, session_key) -> bool:
    return (
        record.get("user") == user_info["user"]
        and record.get("domain") == user_info["domain"]
        and record.get("team") == user_info["team"]
        and record.get("session_key") == session_key
    )


def _notes(user_info, session_key):
    conversation = _conversation_for_key(session_key)
    if conversation is None:
        return []
    notes = []
    queryset = conversation.messages.filter(role=SkillConversationMessage.ROLE_ASSISTANT, content__contains=JOB_RECORD_MARK).order_by("-id")
    for message in queryset:
        parsed = _parse_note_content(message.content)
        if parsed is None:
            continue
        record, output = parsed
        if not _note_matches(record, user_info, session_key):
            continue
        notes.append(_JobNote(message, record, output))
    return notes


def _find_note(user_info, session_key, *, task_id=None, kind=None, fingerprint=None):
    for note in _notes(user_info, session_key):
        if task_id is not None and note.task_id != task_id:
            continue
        if kind is not None and note.kind != kind:
            continue
        if fingerprint is not None and note.record.get("fingerprint") != fingerprint:
            continue
        return note
    return None


def script_status_label(data: dict) -> str:
    status = data.get("status")
    if status not in TERMINAL_STATUSES:
        return "仍在执行"
    if status == STATUS_SUCCESS:
        return "成功"
    if status == STATUS_FAILED and data.get("success_count") and data.get("failed_count"):
        return "部分失败"
    return "失败"


def file_status_label(data: dict) -> str:
    if data.get("status") == STATUS_SUCCESS and not data.get("failed_count"):
        return "成功"
    return "失败"


def _unfinished_file_payload(data: dict, elapsed=None) -> dict:
    payload = {
        "task_id": data["task_id"],
        "status": "仍在执行",
        "targets": [],
        "result_url": _job_result_url(data["task_id"]),
        "kind": "file",
    }
    if elapsed is not None:
        payload["waited_seconds"] = int(max(elapsed, 0))
    return payload


def _file_result_when_query_fails(anchor, elapsed=None) -> str:
    """作业已经提交。查询失败时仍返回作业号和记录链接，不说成一次没有作业的失败。"""

    status = anchor.status if anchor.status not in TERMINAL_STATUSES else STATUS_PENDING
    return _file_tool_result(anchor, {"task_id": anchor.task_id, "status": status}, elapsed)


def _file_tool_result(anchor, data: dict, elapsed=None) -> str:
    """查询正常时，未结束的分发给出作业记录链接。终态仍只说成功或失败。"""

    if anchor is not None:
        anchor.status = data.get("status")
    if data.get("status") not in TERMINAL_STATUSES:
        payload = _unfinished_file_payload(data, elapsed)
        _publish_display(payload)
        _store_display(anchor, payload)
        model = {
            "task_id": payload["task_id"],
            "status": payload["status"],
            "result_url": payload["result_url"],
        }
        if "waited_seconds" in payload:
            model["waited_seconds"] = payload["waited_seconds"]
        return json.dumps(model, ensure_ascii=False)
    label = file_status_label(data)
    if anchor is not None:
        anchor.save(visible=label)
    return label


def _job_result_url(task_id) -> str:
    return f"/job/execution/job-record?id={int(task_id)}"


def _display_payload(data: dict) -> dict:
    job_timed_out = data.get("status") == STATUS_TIMEOUT or data.get("terminal_source") == "execution_timeout"
    targets = []
    for item in data.get("results") or []:
        targets.append(
            {
                "name": item.get("name") or "",
                "ip": item.get("ip") or "",
                "stdout": item.get("stdout") or "",
                "stderr": item.get("stderr") or "",
                "exit_code": item.get("exit_code"),
                "timed_out": job_timed_out or item.get("status") == STATUS_TIMEOUT,
            }
        )
    return {"task_id": data["task_id"], "status": script_status_label(data), "targets": targets}


def _has_script_output(payload: dict) -> bool:
    for item in payload.get("targets") or []:
        if str(item.get("stdout") or "").strip() or str(item.get("stderr") or "").strip() or item.get("timed_out"):
            return True
    return False


def _prepare_display(data: dict, elapsed=None) -> dict:
    payload = _display_payload(data)
    if _has_script_output(payload):
        return payload
    payload["result_url"] = _job_result_url(data["task_id"])
    if elapsed is not None:
        payload["waited_seconds"] = int(max(elapsed, 0))
    return payload


def _publish_display(payload: dict) -> None:
    try:
        _PENDING_DISPLAYS[int(payload["task_id"])] = dict(payload)
    except (TypeError, ValueError, KeyError):
        return


def _store_display(note, payload: dict) -> None:
    if note is None or note.message is None:
        return
    note.output = payload
    note.save(visible=f"作业 {payload['task_id']}：{payload['status']}")


def _model_script_json(payload: dict) -> str:
    body = {
        "task_id": payload["task_id"],
        "status": payload["status"],
        "output_shown": _has_script_output(payload),
    }
    if payload.get("result_url"):
        body["result_url"] = payload["result_url"]
        if "waited_seconds" in payload:
            body["waited_seconds"] = payload["waited_seconds"]
    return json.dumps(body, ensure_ascii=False)


def _write_script_display(user_info, session_key, data, note=None):
    payload = _prepare_display(data)
    note = note or _find_note(user_info, session_key, task_id=data["task_id"])
    if note is not None:
        note.status = data["status"]
    _store_display(note, payload)
    return payload


def _poll(user_info, task_id):
    budget = float(os.getenv("JOB_TOOL_POLL_SECONDS", "300"))
    interval = float(os.getenv("JOB_TOOL_POLL_INTERVAL", "2"))
    started = time.monotonic()
    deadline = started + max(budget, 0)
    while True:
        result = _call(ACTION_QUERY, user_info, {"task_id": task_id})
        elapsed = time.monotonic() - started
        if not result.get("result"):
            return result, elapsed
        if result["data"]["status"] in TERMINAL_STATUSES or time.monotonic() >= deadline:
            return result, elapsed
        time.sleep(interval if interval > 0 else 0.05)


def _remember(user_info, session_key, *, task_id, kind, fingerprint, status):
    """提交后先把作业号写进当前会话，轮询中断后仍能按这个号查询。"""

    record = {
        "task_id": task_id,
        "kind": kind,
        "fingerprint": fingerprint,
        "status": status,
        "submitted_at": _iso(timezone.now()),
        "user": user_info["user"],
        "domain": user_info["domain"],
        "team": user_info["team"],
        "session_key": session_key,
        "watch": None,
    }
    conversation = _conversation_for_key(session_key)
    if conversation is None:
        logger.warning(
            "event=opspilot_job_record_skipped failed_stage=persist error_type=missing_conversation task_id=%s",
            task_id,
        )
        return _JobNote(None, record, None)
    # 延迟导入：本模块被会话服务引用，顶层导入 append_message 会成环。
    from apps.opspilot.services.skill_channel_chat_service import append_message

    visible = f"作业 {task_id}：仍在执行"
    message = append_message(
        conversation,
        SkillConversationMessage.ROLE_ASSISTANT,
        json.dumps(
            [
                {"type": "CUSTOM", "name": JOB_RECORD_NAME, "value": record},
                {"type": "TEXT_MESSAGE_CONTENT", "delta": visible},
            ],
            ensure_ascii=False,
        ),
    )
    return _JobNote(message, record, None)


def _existing_anchor(user_info, session_key, fingerprint, confirmed_rerun, user_text):
    anchor = _find_note(user_info, session_key, fingerprint=fingerprint)
    if anchor is None:
        return None
    if anchor.status not in TERMINAL_STATUSES:
        return {"reuse": anchor}
    if anchor.status in RERUN_STATUSES:
        if not confirmed_rerun or "重新执行" not in user_text and "确认重跑" not in user_text:
            return {
                "ask": True,
                "question": "上次作业已经结束。确认后才会重新提交。",
                "options": ["确认重跑", "不重跑"],
            }
    return None


def _finish_script(user_info, session_key, anchor):
    result, elapsed = _poll(user_info, anchor.task_id)
    if not result.get("result"):
        payload = {
            "task_id": anchor.task_id,
            "status": "仍在执行",
            "targets": [],
            "result_url": _job_result_url(anchor.task_id),
            "waited_seconds": int(max(elapsed, 0)),
        }
    else:
        data = result["data"]
        anchor.status = data["status"]
        payload = _prepare_display(data, elapsed)
    _publish_display(payload)
    _store_display(anchor, payload)
    return _model_script_json(payload)


def _submit_script(user_info, session_key, body, user_text, confirmed_rerun):
    fingerprint = _fingerprint("script", body)
    existing = _existing_anchor(user_info, session_key, fingerprint, confirmed_rerun, user_text)
    if isinstance(existing, dict) and existing.get("ask"):
        return existing
    if isinstance(existing, dict) and existing.get("reuse"):
        return _finish_script(user_info, session_key, existing["reuse"])
    result = _call(ACTION_EXECUTE, user_info, body)
    if not result.get("result"):
        return result
    anchor = _remember(
        user_info,
        session_key,
        task_id=result["data"]["task_id"],
        kind=KIND_SCRIPT,
        fingerprint=fingerprint,
        status=STATUS_PENDING,
    )
    return _finish_script(user_info, session_key, anchor)


def list_job_scripts(config, name: str = ""):
    user_info, _session_key, _configurable = session_context(config)
    return _call(ACTION_LIST_SCRIPTS, user_info, {"name": name or ""})


def list_playbook_scripts(config, name: str = "", path: str = ""):
    user_info, _session_key, _configurable = session_context(config)
    return _call(
        ACTION_LIST_PLAYBOOK_SCRIPTS,
        user_info,
        {"name": name or "", "path": path or ""},
    )


def describe_job_script(config, script_id: int):
    user_info, _session_key, _configurable = session_context(config)
    return _call(ACTION_DESCRIBE_SCRIPT, user_info, {"script_id": script_id})


_CHOSEN_TARGET = re.compile(r"\((manual|node_mgmt):([^)\s]+)\)")
_SOURCE_LABEL = {"manual": "作业管理目标", "node_mgmt": "节点管理目标"}


def _stated_target_source(texts: list[str]) -> str:
    for text in texts:
        node = "节点管理" in text
        manual = "作业管理目标" in text
        if node and not manual:
            return "node_mgmt"
        if manual and not node:
            return "manual"
    return ""


def _chosen_target(texts: list[str]) -> dict | None:
    for text in texts[:1]:
        match = _CHOSEN_TARGET.search(text or "")
        if not match:
            continue
        source, target_id = match.group(1), match.group(2)
        label = _SOURCE_LABEL[source]
        return {
            "use": {"source": source, "id": target_id},
            "message": f"用户已经选定目标。target_source 填{label}，target_ids 填 {target_id}。不要再搜索，不要再问来源。",
        }
    return None


def _use_hit(hit: dict) -> dict:
    label = _SOURCE_LABEL.get(hit.get("source"), "")
    return {
        "use": hit,
        "message": f"只有一个目标。target_source 填{label}，target_ids 填 {hit.get('id')}。不要填 ip 或 name，不要再问来源。",
    }


def search_job_targets(config, keyword: str):
    user_info, session_key, _configurable = session_context(config)
    texts = user_statement_texts(config, session_key)
    chosen = _chosen_target(texts)
    if chosen:
        return chosen
    stated = _stated_target_source(texts)
    result = _call(ACTION_SEARCH_TARGETS, user_info, {"keyword": keyword})
    if not result.get("result"):
        return result
    hits = [hit for hit in result["data"].get("hits") or [] if not stated or hit.get("source") == stated]
    if not hits:
        if stated:
            return {
                "result": False,
                "message": f"在{_SOURCE_LABEL[stated]}里没有找到这个名称或 IP。不要改问另一个来源。",
            }
        return {
            "ask": True,
            "question": "没有找到这个名称或 IP，可能是输错了。请选择目标来源。",
            "options": ["作业管理目标", "节点管理目标"],
        }
    if len(hits) == 1:
        return _use_hit(hits[0])
    return {
        "ask": True,
        "question": "找到多个目标，请选择。执行时 target_ids 只填所选条目的 id，不要填 IP，不要再问来源。",
        "options": [f"{item['name']} {item['ip']} ({item['source']}:{item['id']})" for item in hits],
        "hits": hits,
    }


def list_job_targets(config, source: str, cursor: str = ""):
    user_info, _session_key, _configurable = session_context(config)
    mapped = {"作业管理目标": "manual", "节点管理目标": "node_mgmt"}.get(source, source)
    return _call(ACTION_LIST_TARGETS, user_info, {"source": mapped, "cursor": cursor or ""})


def _confirmed(flag, user_text, phrase):
    return bool(flag) and phrase in user_text


def _library_script_name_confirmed(script_name: str, user_text: str) -> bool:
    """脚本名必须在当前这句里，或当前这句选择了「使用脚本 {名称}」。更早的片段不算。"""

    name = str(script_name or "").strip()
    text = user_text or ""
    if not name or not text:
        return False
    if f"使用脚本 {name}" in text:
        return True
    return name in text


def run_library_script(config, *, script_id, target_source, target_ids, params=None, danger_confirmed=False, confirmed_rerun=False, name=""):
    user_info, session_key, _configurable = session_context(config)
    user_text = current_user_text(config, session_key)
    if not script_id:
        listed = list_job_scripts(config, name)
        return listed
    body = {
        "mode": "library",
        "script_id": script_id,
        "target_source": {"作业管理目标": "manual", "节点管理目标": "node_mgmt"}.get(target_source, target_source),
        "target_ids": target_ids,
        "params": params or [],
        "name": name or "",
        "danger_confirmed": _confirmed(danger_confirmed, user_text, "确认执行"),
    }
    described = describe_job_script(config, script_id)
    if not isinstance(described, dict) or not described.get("result"):
        return described if isinstance(described, dict) else {"result": False, "message": "脚本不存在或不属于当前组织"}
    script_name = str(described["data"].get("name") or "")
    script_type = str(described["data"].get("script_type") or "")
    fingerprint = _fingerprint("script", body)
    anchor = _find_note(user_info, session_key, kind=KIND_SCRIPT, fingerprint=fingerprint)
    if anchor is None and not _library_script_name_confirmed(script_name, user_text):
        return {
            "ask": True,
            "question": f"是否使用脚本「{script_name}」（{script_type}）？",
            "options": [f"使用脚本 {script_name}", "不使用这个脚本"],
        }
    return _submit_script(user_info, session_key, body, user_text, confirmed_rerun)


def _custom_script_stated(script_type: str, content: str, texts: list[str]) -> bool:
    pattern = _TYPE_PATTERNS.get(script_type)
    if not pattern or not content:
        return False
    return any(content in text and pattern.search(text) for text in texts)


def run_custom_script(
    config,
    *,
    script_type,
    script_content,
    target_source,
    target_ids,
    danger_confirmed=False,
    confirmed_rerun=False,
    name="",
    timeout=CUSTOM_TIMEOUT_SECONDS,
):
    user_info, session_key, _configurable = session_context(config)
    user_text = current_user_text(config, session_key)
    content = str(script_content or "").strip()
    if not _custom_script_stated(script_type, content, user_statement_texts(config, session_key)):
        return {
            "result": False,
            "message": "本会话里还没有同一句用户原话同时包含这种脚本类型和这段正文。不要代写，不要编指定句式让用户重说，也不要重新询问已经选过的目标。",
        }
    try:
        timeout_value = int(timeout or CUSTOM_TIMEOUT_SECONDS)
    except (TypeError, ValueError):
        timeout_value = CUSTOM_TIMEOUT_SECONDS
    if timeout_value != CUSTOM_TIMEOUT_SECONDS and str(timeout_value) not in user_text:
        timeout_value = CUSTOM_TIMEOUT_SECONDS
    job_name = str(name or "").strip()
    if not job_name or job_name == content or job_name not in user_text:
        job_name = "自定义脚本"
    body = {
        "mode": "custom",
        "script_type": script_type,
        "script_content": content,
        "target_source": {"作业管理目标": "manual", "节点管理目标": "node_mgmt"}.get(target_source, target_source),
        "target_ids": target_ids,
        "name": job_name,
        "timeout": timeout_value,
        "danger_confirmed": _confirmed(danger_confirmed, user_text, "确认执行"),
    }
    return _submit_script(user_info, session_key, body, user_text, confirmed_rerun)


def _overwrite_strategy(user_text: str):
    """只认当前这句。更早的「覆盖」或「跳过」不能替这一次分发做选择。"""

    overwrite = "覆盖" in user_text or re.search(r"(?i)(?<![A-Za-z])overwrite(?![A-Za-z])", user_text or "")
    skip = "跳过" in user_text or re.search(r"(?i)(?<![A-Za-z])skip(?![A-Za-z])", user_text or "")
    if overwrite and not skip:
        return "overwrite"
    if skip and not overwrite:
        return "skip"
    return None


# 路径按最长连续片段截取，父目录不能从更长路径里截出来。
_UNIX_PATH_TOKEN = re.compile(r"(?<![A-Za-z0-9./])(/(?:[\w.@+-]+/)*[\w.@+-]+)")
_WIN_PATH_TOKEN = re.compile(r"(?<![A-Za-z0-9\\])([A-Za-z]:\\(?:[^\\/:*?\"<>|\s]+\\)*[^\\/:*?\"<>|\s]*)")
_PATH_EDGE = ".,;:，。、)）]】\"'`"


def _normalize_stated_path(path: str) -> str:
    text = str(path or "").strip().strip("`\"'")
    text = text.rstrip(_PATH_EDGE)
    if len(text) > 1:
        text = text.rstrip("/\\")
    return text


def _path_tokens(text: str) -> list[str]:
    if not text:
        return []
    found = []
    for pattern in (_UNIX_PATH_TOKEN, _WIN_PATH_TOKEN):
        for match in pattern.findall(text):
            token = _normalize_stated_path(match)
            if token and token not in found:
                found.append(token)
    return found


def _earlier_statements(current: str, statements: list[str]) -> list[str]:
    """去掉排在最前的当前这句，剩下的是更早的用户原话。"""

    skipped = False
    current_text = (current or "").strip()
    earlier = []
    for text in statements or []:
        if not isinstance(text, str):
            continue
        if not skipped and text.strip() == current_text:
            skipped = True
            continue
        earlier.append(text)
    return earlier


def _just_confirmed_path_tokens(current: str, statements: list[str]) -> list[str]:
    """当前这句在确认路径时，只接受最近一句里说清的完整路径，不接受更早的路径。"""

    text = current or ""
    if not re.search(r"确认路径|就用这个路径|使用这个路径|目标路径就", text):
        return []
    for statement in _earlier_statements(text, statements):
        tokens = _path_tokens(statement)
        if tokens:
            return tokens
    return []


def _target_path_accepted(path: str, current: str, statements: list[str]) -> bool:
    """目标路径必须是当前这句里的完整路径，或与某一句用户原话整句相同。

    模型传入的更短父目录、以及只在更早长句里出现过的路径，都不能通过。
    """

    wanted = _normalize_stated_path(path)
    if not wanted:
        return False
    current_tokens = _path_tokens(current)
    if wanted in current_tokens:
        return True
    if current_tokens:
        return False
    for text in _earlier_statements(current, statements):
        if _normalize_stated_path(text) == wanted:
            return True
    return wanted in _just_confirmed_path_tokens(current, statements)


def _staged_reason(session_key: str) -> str:
    return f"{DISTRIBUTE_STAGE_REASON_PREFIX}{session_key}"[:255]


def _staged_queryset(owner_key, team_id, session_key):
    return ChatAttachment.objects.filter(
        owner_key=owner_key,
        team_id=str(team_id),
        failure_reason=_staged_reason(session_key),
        created_at__gt=timezone.now() - timedelta(days=STAGED_FILE_DAYS),
    )


def list_staged_distribute_files(*, owner_key, team_id, session_key):
    """只返回当前用户、当前组织、当前会话的文件名。不含正文。"""

    if not session_key:
        return []
    rows = _staged_queryset(owner_key, team_id, session_key).order_by("id")
    return [{"id": row.id, "name": row.original_name, "size": row.size} for row in rows]


_NAMED_FILE = re.compile(r"(?<![\w.])([\w.-]+\.[A-Za-z][A-Za-z0-9]{0,7})(?![\w.])")


def _chat_history_user_texts(config) -> list[str]:
    """技能测试没有会话记录，上一句只留在请求的 chat_history 里。"""

    configurable = configurable_from_config(config)
    graph_request = configurable.get("graph_request")
    history = getattr(graph_request, "chat_history", None) if graph_request is not None else None
    if history is None:
        history = configurable.get("chat_history") or []
    texts = []
    for item in history or []:
        if isinstance(item, dict):
            event = item.get("event") or item.get("role") or ""
            message = item.get("message") or item.get("content") or ""
        else:
            event = getattr(item, "event", "") or getattr(item, "role", "") or ""
            message = getattr(item, "message", "") or getattr(item, "content", "") or ""
        if str(event).strip().lower() in {"user", "human"} and isinstance(message, str):
            texts.append(message)
    return texts


def _mentions_other_filename(texts, staged_name: str) -> bool:
    staged = staged_name.casefold()
    for text in texts:
        for match in _NAMED_FILE.findall(text or ""):
            if match.casefold() != staged:
                return True
    return False


def _parse_file_ids(raw):
    if isinstance(raw, str):
        raw = [item for item in raw.split(",") if item.strip()]
    try:
        return [int(item) for item in raw or []]
    except (TypeError, ValueError):
        return None


def _staged_files(user_info, session_key, file_ids, user_text, statements=None):
    owner = _owner_key(user_info)
    queryset = _staged_queryset(owner, user_info["team"], session_key)
    texts = []
    for item in [user_text, *(statements or [])]:
        if isinstance(item, str) and item.strip() and item not in texts:
            texts.append(item)
    if file_ids:
        rows = list(queryset.filter(id__in=file_ids))
        if len(rows) != len(set(file_ids)):
            return None, {"result": False, "message": "暂存文件不在当前用户的当前会话里"}
    else:
        available = list(queryset.order_by("id"))
        rows = [row for row in available if row.original_name and any(row.original_name in text for text in texts)]
        names = [row.original_name for row in rows]
        if len(names) != len(set(names)):
            return None, {
                "ask": True,
                "question": "有多个同名暂存文件，请选择文件编号。",
                "options": [f"{row.id}:{row.original_name}" for row in rows],
            }
        if not rows and len(available) == 1 and not _mentions_other_filename(texts, available[0].original_name):
            rows = available
        if not rows and len(available) > 1:
            return None, {
                "ask": True,
                "question": "请说明要分发哪个文件。",
                "options": [row.original_name for row in available],
            }
        if not rows:
            return None, {"result": False, "message": "当前会话没有可分发的暂存文件"}
    files = []
    for row in rows:
        with row.file.open("rb") as handle:
            files.append((row.original_name, handle.read()))
    return (rows, files), None


def _publish_job_file(file_key: str, data: bytes, filename: str) -> None:
    """确认分发后才连接对象存储。启动 OpsPilot 不加载作业应用，也不连接这条通道。"""

    from asgiref.sync import async_to_sync

    from apps.rpc.jetstream import JetStreamService

    async def _put():
        service = JetStreamService()
        await service.connect()
        try:
            await service.put(file_key, data, description=filename)
        finally:
            await service.close()

    async_to_sync(_put)()


def _discard_job_file(file_key: str) -> None:
    """提交被拒绝时删掉刚放入的对象。只在这次失败时连接对象存储。"""

    from asgiref.sync import async_to_sync

    from apps.rpc.jetstream import JetStreamService

    async def _delete():
        service = JetStreamService()
        await service.connect()
        try:
            await service.delete(file_key)
        finally:
            await service.close()

    try:
        async_to_sync(_delete)()
    except Exception as exc:
        logger.warning(
            "event=opspilot_job_file_discard_failed failed_stage=distribute error_type=%s",
            type(exc).__name__,
        )


def _commit_distribution(user_info, body, files):
    prepared = _rpc(
        ACTION_DISTRIBUTE,
        user_info,
        {**body, "prepare": True},
        files=[{"name": name, "size": len(data)} for name, data in files],
    )
    if not prepared.get("result") or prepared.get("code") != "ready":
        return prepared
    published = []
    entries = []
    try:
        for name, data in files:
            file_key = new_job_file_key(name)
            _publish_job_file(file_key, data, name)
            published.append(file_key)
            entries.append({"name": name, "file_key": file_key})
    except Exception as exc:
        logger.warning(
            "event=opspilot_job_file_publish_failed failed_stage=distribute error_type=%s",
            type(exc).__name__,
        )
        for file_key in published:
            _discard_job_file(file_key)
        return {"result": False, "message": "文件写入作业平台失败"}
    created = _rpc(ACTION_DISTRIBUTE, user_info, body, files=entries)
    # 调度失败或响应丢失时作业记录可能已经引用这些对象，不能删。
    if not created.get("result") and created.get("code") != "dispatch_failed" and created.get("message") != "作业平台暂时不可用":
        for file_key in published:
            _discard_job_file(file_key)
    return created


def distribute_staged_files(
    config,
    *,
    file_ids=None,
    target_source="",
    target_ids=None,
    target_path="",
    danger_confirmed=False,
    name="",
):
    user_info, session_key, configurable = session_context(config)
    user_text = current_user_text(config, session_key)
    statements = user_statement_texts(config, session_key)
    server_ids = _parse_file_ids(configurable.get("distribute_file_ids") or [])
    if server_ids:
        selected = server_ids
    else:
        parsed = _parse_file_ids(file_ids or [])
        # 模型编的编号不能挡住按文件名或本会话唯一文件继续找。
        selected = parsed if parsed else []
    loaded, error = _staged_files(user_info, session_key, selected, user_text, statements)
    if error:
        return error
    rows, files = loaded
    path = str(target_path or "").strip()
    if not _target_path_accepted(path, user_text, statements):
        return {"ask": True, "question": "请给出文件要放到的目标路径。", "options": []}
    strategy = _overwrite_strategy(user_text)
    if strategy is None:
        return {
            "ask": True,
            "question": "分发前不会检查目标磁盘。如果目录里已经有同名文件，覆盖还是跳过？",
            "options": ["覆盖", "跳过"],
        }
    body = {
        "target_source": {"作业管理目标": "manual", "节点管理目标": "node_mgmt"}.get(target_source, target_source),
        "target_ids": target_ids,
        "target_path": path,
        "overwrite_strategy": strategy,
        "name": name or rows[0].original_name,
        "danger_confirmed": _confirmed(danger_confirmed, user_text, "确认执行"),
    }
    fingerprint = _fingerprint("file", body, file_ids=[row.id for row in rows])
    existing = _existing_anchor(user_info, session_key, fingerprint, False, user_text)
    if isinstance(existing, dict) and existing.get("reuse"):
        result = _call(ACTION_QUERY, user_info, {"task_id": existing["reuse"].task_id})
        if result.get("result"):
            return _file_tool_result(existing["reuse"], result["data"])
        return _file_result_when_query_fails(existing["reuse"])
    created = _commit_distribution(user_info, body, files)
    if not created.get("result"):
        if created.get("code") in {"need_path", "need_overwrite", "confirm", "forbidden"}:
            return created
        return "失败"
    anchor = _remember(
        user_info,
        session_key,
        task_id=created["data"]["task_id"],
        kind=KIND_FILE,
        fingerprint=fingerprint,
        status=STATUS_PENDING,
    )
    result, elapsed = _poll(user_info, anchor.task_id)
    if not result.get("result"):
        return _file_result_when_query_fails(anchor, elapsed)
    return _file_tool_result(anchor, result["data"], elapsed)


def query_job(config, task_id=None):
    user_info, session_key, _configurable = session_context(config)
    anchor = _find_note(user_info, session_key, task_id=task_id) if task_id else None
    if anchor is None:
        anchor = _find_note(user_info, session_key)
    if anchor is None:
        return {"result": False, "message": "当前会话没有作业"}
    result = _call(ACTION_QUERY, user_info, {"task_id": anchor.task_id})
    if anchor.kind == KIND_SCRIPT and not result.get("result"):
        payload = {
            "task_id": anchor.task_id,
            "status": "仍在执行",
            "targets": [],
            "result_url": _job_result_url(anchor.task_id),
        }
        _publish_display(payload)
        _store_display(anchor, payload)
        return _model_script_json(payload)
    if not result.get("result"):
        return {"task_id": anchor.task_id, "status": "仍在执行"}
    data = result["data"]
    anchor.status = data["status"]
    if anchor.kind == KIND_SCRIPT:
        payload = _prepare_display(data)
        _publish_display(payload)
        _store_display(anchor, payload)
        return _model_script_json(payload)
    return _file_tool_result(anchor, data)


def schedule_job_watch(config, task_id=None, interval_minutes=DEFAULT_WATCH_MINUTES):
    user_info, session_key, _configurable = session_context(config)
    user_text = current_user_text(config, session_key)
    if "定时检查" not in user_text:
        return {
            "ask": True,
            "question": "作业还没结束。要不要按间隔继续查看同一个作业号？不会重新执行。",
            "options": ["定时检查", "不用检查"],
        }
    try:
        interval = int(interval_minutes or DEFAULT_WATCH_MINUTES)
    except (TypeError, ValueError):
        interval = DEFAULT_WATCH_MINUTES
    if interval != DEFAULT_WATCH_MINUTES and str(interval) not in user_text:
        interval = DEFAULT_WATCH_MINUTES
    interval = min(max(interval, 1), WATCH_HOURS * 60)
    anchor = _find_note(user_info, session_key, task_id=task_id, kind=KIND_SCRIPT) if task_id else None
    if anchor is None and not task_id:
        anchor = _find_note(user_info, session_key, kind=KIND_SCRIPT)
    if anchor is None:
        return {"result": False, "message": "当前会话没有可检查的脚本作业"}
    deadline = anchor.submitted_at + timedelta(hours=WATCH_HOURS)
    if timezone.now() >= deadline or anchor.status in TERMINAL_STATUSES:
        return {"result": False, "message": "作业已经结束或超过检查期限"}
    anchor.record["watch"] = {
        "interval_minutes": interval,
        "next_run_at": _iso(timezone.now() + timedelta(minutes=interval)),
        "deadline_at": _iso(deadline),
        "active": True,
    }
    anchor.save()
    return {"task_id": anchor.task_id, "status": "已安排定时检查", "interval_minutes": interval}


def latest_display_payload(task_id):
    """界面回写展示块。刚提交的结果先走内存，没有时再查会话。AGUI 流在异步线程里，同步查库要换到独立线程。"""

    try:
        key = int(task_id)
    except (TypeError, ValueError):
        return None
    pending = _PENDING_DISPLAYS.pop(key, None)
    if pending is not None:
        return pending
    try:
        asyncio.get_running_loop()
        in_async = True
    except RuntimeError:
        in_async = False
    if not in_async:
        return _latest_display_payload(task_id)
    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(_latest_display_payload, task_id).result()


def _latest_display_payload(task_id):
    close_old_connections()
    try:
        try:
            task_mark = f'"task_id": {int(task_id)}'
        except (TypeError, ValueError):
            return None
        message = (
            SkillConversationMessage.objects.filter(content__contains=task_mark).filter(content__contains=JOB_OUTPUT_NAME).order_by("-id").first()
        )
        if message is None:
            return None
        parsed = _parse_note_content(message.content)
        if parsed is None:
            return None
        return parsed[1]
    finally:
        close_old_connections()


def _due_notes(now):
    queryset = SkillConversationMessage.objects.filter(
        role=SkillConversationMessage.ROLE_ASSISTANT,
        created_at__gte=now - timedelta(hours=WATCH_HOURS + 1),
        content__contains=JOB_RECORD_MARK,
    ).order_by("id")
    due = []
    for message in queryset:
        parsed = _parse_note_content(message.content)
        if parsed is None:
            continue
        record, output = parsed
        watch = record.get("watch")
        if not isinstance(watch, dict) or watch.get("active") is not True:
            continue
        try:
            next_run_at = _parse_iso(watch.get("next_run_at"))
        except (TypeError, ValueError):
            continue
        if next_run_at <= now:
            due.append(_JobNote(message, record, output))
    return due


def scan_job_watches(now=None):
    """到期后只查询原作业号，把终态写进会话，不调用模型。"""

    now = now or timezone.now()
    checked = 0
    for note in _due_notes(now):
        checked += 1
        watch = note.record["watch"]
        user_info = {
            "user": note.record["user"],
            "domain": note.record["domain"],
            "team": note.record["team"],
            "include_children": False,
        }
        try:
            result = _call(ACTION_QUERY, user_info, {"task_id": note.task_id})
        except Exception as exc:
            logger.warning(
                "event=opspilot_job_watch_failed failed_stage=query task_id=%s error_type=%s",
                note.task_id,
                type(exc).__name__,
            )
            watch["next_run_at"] = _iso(now + timedelta(minutes=int(watch["interval_minutes"])))
            note.save()
            continue
        if not result.get("result"):
            watch["next_run_at"] = _iso(now + timedelta(minutes=int(watch["interval_minutes"])))
            note.save()
            continue
        data = result["data"]
        terminal = data["status"] in TERMINAL_STATUSES
        try:
            deadline_at = _parse_iso(watch["deadline_at"])
        except (TypeError, ValueError):
            deadline_at = note.submitted_at + timedelta(hours=WATCH_HOURS)
        if terminal or now >= deadline_at:
            watch["active"] = False
            _write_script_display(user_info, note.session_key, data, note=note)
        else:
            watch["next_run_at"] = _iso(now + timedelta(minutes=int(watch["interval_minutes"])))
            note.status = data["status"]
            note.save()
    return checked


def _max_upload_bytes() -> int:
    try:
        megabytes = int(os.getenv("JOB_MAX_UPLOAD_FILE_SIZE_MB", "1024"))
    except (TypeError, ValueError):
        megabytes = 1024
    return megabytes * 1024 * 1024


def stage_distribute_file(*, owner_key, team_id, session_key, filename, data: bytes):
    if not session_key:
        raise JobToolError("当前会话缺失，不能暂存文件")
    if not isinstance(data, (bytes, bytearray)) or not data:
        raise JobToolError("文件内容为空")
    if len(data) > _max_upload_bytes():
        raise JobToolError("文件超过作业平台上传上限")
    safe_name = os.path.basename(str(filename or "").replace("\\", "/")).strip() or "file"
    # 不走对话附件的解析入口。状态保持失败，模型读不到正文；失败原因只用来认出这份暂存。
    return ChatAttachment.objects.create(
        file=ContentFile(bytes(data), name=safe_name[:255]),
        original_name=safe_name[:255],
        mime_type="application/octet-stream",
        size=len(data),
        status=ChatAttachment.STATUS_FAILED,
        parsed_text="",
        failure_reason=_staged_reason(session_key),
        owner_key=owner_key,
        team_id=str(team_id),
        conversation=_conversation_for_key(session_key),
    )


def cleanup_staged_files():
    expired = ChatAttachment.objects.filter(
        failure_reason__startswith=DISTRIBUTE_STAGE_REASON_PREFIX,
        created_at__lte=timezone.now() - timedelta(days=STAGED_FILE_DAYS),
    )
    removed = 0
    for row in expired.iterator():
        if row.file:
            row.file.delete(save=False)
        row.delete()
        removed += 1
    return removed


def owned_distribute_ids(raw_ids, *, owner_key, team_id, session_key):
    try:
        ids = [int(item) for item in raw_ids or []]
    except (TypeError, ValueError):
        return []
    if not ids or not session_key:
        return []
    return list(_staged_queryset(owner_key, team_id, session_key).filter(id__in=ids).values_list("id", flat=True))


def skill_has_job_mgmt(skill) -> bool:
    for tool in getattr(skill, "tools", None) or []:
        if not isinstance(tool, dict):
            continue
        params = tool.get("params") if isinstance(tool.get("params"), dict) else {}
        if tool.get("name") == "job_mgmt" or params.get("url") == "langchain:job_mgmt":
            return True
    return False
