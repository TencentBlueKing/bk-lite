"""任务完成回调服务

作业进入终态后，按调用方在触发时选择的通道（callback_type）投递执行结果：
- web:  HTTP POST 到 callback_url（原 web 层方式，带 HMAC 签名，Celery 重试）
- nats: publish 到 callback_subject（参考 ansible 的 callback_config.subject，fire-and-forget）
- both: 两个通道都投

两个通道都走 Celery 任务异步执行（任务定义在 tasks.py，Celery autodiscover 只扫描 apps/*/tasks.py）：
一是不阻塞调用 send_callback 的 NATS 回调/取消接口（它们运行在 nats_listener 的异步上下文）；
二是 NATS publish 走 asyncio.run，必须在 Celery worker 等同步上下文中执行。
"""

import os

from celery import current_app

from apps.core.logger import job_logger as logger
from apps.job_mgmt.constants import CallbackType
from nats_client.clients import publish_sync


def build_callback_payload(execution) -> dict:
    """构造回调结果（nats 通道使用，含逐主机明细）。

    task_id 与触发作业时同步返回的 task_id 一致，消费方据此关联回原始请求（如告警）。
    """
    return {
        "task_id": execution.id,
        "name": execution.name,
        "job_type": execution.job_type,
        "trigger_source": execution.trigger_source,
        "status": execution.status,
        "total_count": execution.total_count,
        "success_count": execution.success_count,
        "failed_count": execution.failed_count,
        "started_at": execution.started_at.isoformat() if execution.started_at else None,
        "finished_at": execution.finished_at.isoformat() if execution.finished_at else None,
        "execution_results": execution.execution_results or [],
    }


def send_callback(execution) -> None:
    """任务终态后的统一回调入口，按 callback_type 分发到对应通道。"""
    callback_type = getattr(execution, "callback_type", None) or CallbackType.WEB

    if CallbackType.use_web(callback_type):
        _send_web_callback(execution)

    if CallbackType.use_nats(callback_type):
        _send_nats_callback(execution)


def _send_web_callback(execution) -> None:
    """web 通道：仅在 callback_url 存在时，通过 Celery 异步任务做 HTTP 回调。

    失败时由 Celery 内置重试机制处理（指数退避，最多 5 次）。
    """
    callback_url = getattr(execution, "callback_url", None)
    if not callback_url:
        return

    payload = {
        "task_id": execution.id,
        "status": execution.status,
        "total_count": execution.total_count,
        "success_count": execution.success_count,
        "failed_count": execution.failed_count,
        "finished_at": execution.finished_at.isoformat() if execution.finished_at else None,
    }

    logger.info(f"[callback][web] 提交回调任务: execution_id={execution.id}, url={callback_url}")
    current_app.send_task("apps.job_mgmt.tasks.do_callback_task", args=[callback_url, payload, execution.id])


def _send_nats_callback(execution) -> None:
    """nats 通道：仅在 callback_subject 存在时，通过 Celery 异步任务 publish 结果到该主题。"""
    subject = getattr(execution, "callback_subject", None)
    if not subject:
        logger.warning(f"[callback][nats] callback_type 含 nats 但未配置 callback_subject，跳过: execution_id={execution.id}")
        return

    payload = build_callback_payload(execution)
    logger.info(f"[callback][nats] 提交回调任务: execution_id={execution.id}, subject={subject}")
    current_app.send_task("apps.job_mgmt.tasks.do_nats_callback_task", args=[subject, payload, execution.id])


def publish_job_result_to_subject(subject: str, payload: dict) -> None:
    """把作业结果以 RPC 信封格式 publish 到指定 NATS 主题（在 Celery worker 同步上下文中调用）。

    subject 形如 ``bklite.alert_job_result``：拆成 namespace + 方法名，消费方按
    ``@nats_client.register def alert_job_result(data): ...`` 接收（与 ansible_task_callback 同构）。
    无命名空间前缀时用默认命名空间。
    """
    namespace, sep, method = subject.partition(".")
    if not sep:
        namespace, method = os.getenv("NATS_NAMESPACE", "bklite"), subject
    publish_sync(namespace, method, data=payload)
