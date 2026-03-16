from concurrent.futures import ThreadPoolExecutor, as_completed

from django.utils import timezone

from apps.core.logger import job_logger as logger
from apps.job_mgmt.constants import ExecutionStatus, TargetSource
from apps.job_mgmt.services import ExecutionTaskBaseService
from apps.rpc.executor import Executor


class PlaybookExecution(ExecutionTaskBaseService):
    def __init__(self, execution_id):
        super().__init__(execution_id, "execute_playbook_task")

    def run(self):
        logger.info(f"[{self.task_name}] 开始执行Playbook任务: execution_id={self.execution_id}")

        execution, target_list = self.prepare_execution()
        if not execution:
            return

        # 检查 Playbook 是否存在
        if not execution.playbook:
            logger.error(f"[{self.task_name}] Playbook 不存在: execution_id={self.execution_id}")
            self.update_execution_status(execution, ExecutionStatus.FAILED, finished_at=timezone.now())
            return

        # 并发执行
        results = []
        with ThreadPoolExecutor(max_workers=min(self.MAX_WORKERS, len(target_list))) as pool:
            futures = {pool.submit(self.execute_playbook_on_target, t, execution.target_source, execution.timeout): t for t in target_list}
            for future in as_completed(futures):
                target_info = futures[future]
                try:
                    result = future.result()
                    results.append(result)
                    logger.info(f"[{self.task_name}] 目标 {target_info.get('name')} 执行完成: status={result['status']}")
                except Exception as e:
                    logger.exception(f"[{self.task_name}] 目标 {target_info.get('name')} 执行异常: {e}")
                    results.append(
                        {
                            "target_key": target_info.get("node_id") or str(target_info.get("target_id", "")),
                            "name": target_info.get("name", ""),
                            "ip": target_info.get("ip", ""),
                            "status": ExecutionStatus.FAILED,
                            "error_message": str(e),
                        }
                    )

        self.finalize_execution(execution, self.task_name, results)

    def execute_playbook_on_target(self, target_info: dict, target_source: str, timeout: int) -> dict:
        """在单个目标上执行 Playbook

        Playbook 简化设计：直接执行 playbook.yml，无需额外参数
        注意：实际实现需要先下载 Playbook 压缩包到目标并解压

        Args:
            target_info: 目标信息字典
            target_source: 目标来源 (node_mgmt / manual)
            timeout: 超时时间
        """
        target_key = target_info.get("node_id") or str(target_info.get("target_id", ""))
        target_name = target_info.get("name", "")
        target_ip = target_info.get("ip", "")

        result = {
            "target_key": target_key,
            "name": target_name,
            "ip": target_ip,
            "status": ExecutionStatus.PENDING,
            "stdout": "",
            "stderr": "",
            "exit_code": None,
            "error_message": "",
            "started_at": timezone.now().isoformat(),
            "finished_at": "",
        }

        try:
            # 构建 ansible-playbook 命令
            command = "ansible-playbook playbook.yml -i localhost, -c local"

            if target_source in (TargetSource.NODE_MGMT, TargetSource.SYNC):
                node_id = target_info.get("node_id")
                executor = Executor(node_id)
                exec_result = executor.execute_local(command, timeout=timeout, shell="bash")
            else:
                target_id = target_info.get("target_id")
                ssh_creds = self.get_ssh_credentials(target_id)
                if not ssh_creds:
                    raise ValueError(f"无法获取目标凭据: target_id={target_id}")

                executor = Executor(ssh_creds["node_id"])
                exec_result = executor.execute_ssh(
                    command=command,
                    host=ssh_creds["host"],
                    username=ssh_creds["username"],
                    password=ssh_creds["password"],
                    private_key=ssh_creds["private_key"],
                    timeout=timeout,
                    port=ssh_creds["port"],
                )

            if isinstance(exec_result, dict):
                result["stdout"] = exec_result.get("stdout", "")
                result["stderr"] = exec_result.get("stderr", "")
                result["exit_code"] = exec_result.get("exit_code", exec_result.get("code", -1))
                result["status"] = ExecutionStatus.SUCCESS if result["exit_code"] == 0 else ExecutionStatus.FAILED
            else:
                result["stdout"] = str(exec_result)
                result["exit_code"] = 0
                result["status"] = ExecutionStatus.SUCCESS

        except Exception as e:
            result["error_message"] = self.format_error_message(e)
            result["stderr"] = result["error_message"]
            result["status"] = ExecutionStatus.FAILED
            logger.exception(f"目标 {target_name}({target_ip}) Playbook执行失败")

        result["finished_at"] = timezone.now().isoformat()
        return result
