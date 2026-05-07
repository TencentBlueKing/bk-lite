"""任务完成回调服务"""

import threading
import time

import requests

from apps.core.logger import job_logger as logger


def send_callback(execution) -> None:
    """
    任务完成后通过 HTTP POST 回调通知调用方。

    仅在 execution.callback_url 存在时触发。
    使用后台线程执行，不阻塞主流程。
    失败时指数退避重试最多 3 次（1s → 2s → 4s）。
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

    thread = threading.Thread(
        target=_do_callback,
        args=(callback_url, payload, execution.id),
        daemon=True,
    )
    thread.start()


def _do_callback(url: str, payload: dict, execution_id: int, max_retries: int = 3) -> None:
    """执行回调 POST 请求，失败时指数退避重试。"""
    for attempt in range(max_retries + 1):
        try:
            resp = requests.post(url, json=payload, timeout=10)
            if 200 <= resp.status_code < 300:
                logger.info(f"[callback] 回调成功: execution_id={execution_id}, url={url}")
                return
            else:
                logger.warning(f"[callback] 回调返回非 2xx: execution_id={execution_id}, " f"status_code={resp.status_code}, attempt={attempt + 1}")
        except Exception as e:
            logger.warning(f"[callback] 回调异常: execution_id={execution_id}, " f"attempt={attempt + 1}, error={e}")

        if attempt < max_retries:
            delay = 2**attempt  # 1s, 2s, 4s
            time.sleep(delay)

    logger.warning(f"[callback] 回调重试耗尽: execution_id={execution_id}, url={url}")
