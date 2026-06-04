# -*- coding: utf-8 -*-
"""
Ansible Executor NATS RPC 封装

通过 NATS 调用 Ansible Executor 的 adhoc 接口，
实现远程 SSH/WinRM 命令执行。
"""

import json
import uuid
import logging
from typing import Any, Dict, Optional

from nats.errors import NoRespondersError

from core.nats_utils import nats_request

logger = logging.getLogger("stargazer.ansible_rpc")


async def ansible_adhoc(
    ansible_node_id: str,
    host_credentials: list,
    module: str = "shell",
    module_args: str = "",
    hosts: str = "all",
    execute_timeout: int = 60,
    extra_vars: Optional[Dict[str, Any]] = None,
    callback: Optional[Dict[str, Any]] = None,
    task_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    通过 NATS RPC 调用 Ansible Executor 执行 adhoc 命令

    Args:
        ansible_node_id: Ansible Executor 实例 ID（与云区域绑定）
        host_credentials: 主机凭据列表，格式:
            [{"host": "10.0.0.1", "user": "root", "password": "xxx",
              "connection": "ssh", "port": 22}]
        module: Ansible 模块名 (shell / win_shell / raw / ping 等)
        module_args: 模块参数（脚本内容或命令）
        hosts: 主机匹配表达式，默认 all
        execute_timeout: 单次执行超时（秒）
        extra_vars: 额外变量
        task_id: 任务 ID，不传则自动生成

    Returns:
        Ansible Executor 返回的执行结果

    Raises:
        TimeoutError: NATS 请求超时
        Exception: 其他异常
    """
    if not task_id:
        task_id = uuid.uuid4().hex

    request_data = {
        "inventory": "",
        "inventory_content": None,
        "host_credentials": host_credentials,
        "private_key_content": None,
        "private_key_passphrase": None,
        "hosts": hosts,
        "module": module,
        "module_args": module_args,
        "extra_vars": extra_vars or {},
        "callback": callback or {},
        "task_id": task_id,
        "execute_timeout": execute_timeout,
    }

    subject = f"ansible.adhoc.{ansible_node_id}"
    payload = json.dumps({"args": [request_data], "kwargs": {}}).encode()

    nats_timeout = execute_timeout + 30

    logger.info(
        f"Ansible adhoc: node={ansible_node_id}, module={module}, "
        f"hosts={len(host_credentials)}, timeout={execute_timeout}s"
    )

    try:
        result = await nats_request(subject, payload=payload, timeout=nats_timeout)
    except NoRespondersError:
        # 没有任何 ansible-executor 订阅该 subject：通常是 ansible_node_id 配置错误
        # （例如落到了 "default"）或对应云区域的执行节点离线。立即报错，避免空等超时。
        logger.error(
            f"Ansible adhoc no responders: subject={subject}, node={ansible_node_id}, "
            f"task_id={task_id}. 没有 ansible-executor 订阅该节点，请检查 ansible_node_id "
            f"是否正确以及对应云区域的执行节点是否在线"
        )
        raise RuntimeError(
            f"No ansible executor subscribed for node '{ansible_node_id}' "
            f"(subject={subject}); check ansible_node_id / cloud region binding "
            f"and that the executor is online"
        )
    except TimeoutError:
        logger.error(
            f"Ansible adhoc NATS timeout: node={ansible_node_id}, task_id={task_id}, "
            f"timeout={nats_timeout}s"
        )
        raise
    except Exception as e:
        logger.error(
            f"Ansible adhoc NATS error: node={ansible_node_id}, task_id={task_id}, "
            f"error={type(e).__name__}: {e}"
        )
        raise

    logger.info(f"Ansible adhoc completed: task_id={task_id}, success={result.get('success')}")
    return result
