from concurrent.futures import ThreadPoolExecutor, as_completed

from django.utils import timezone

from apps.core.logger import job_logger as logger
from apps.job_mgmt.constants import ExecutionStatus, ScriptType, TargetSource
from apps.job_mgmt.services.dangerous_checker import DangerousChecker
from apps.job_mgmt.services.execution_base_service import ExecutionTaskBaseService
from apps.rpc.executor import Executor


class ScriptExecutionRunner(ExecutionTaskBaseService):
    def __init__(self, execution_id: int):
        super().__init__(execution_id, "execute_script_task")

    def run(self):
        logger.info(f"[{self.task_name}] 开始执行脚本任务: execution_id={self.execution_id}")
        execution, target_list = self.prepare_execution()
        if not execution:
            return

        if self._handle_dangerous_command(execution, target_list):
            return

        script_content = self.merge_script_with_params(execution.script_content, execution.params, execution.script_type)
        if self._run_via_ansible_if_needed(execution, target_list, script_content):
            return

        results = self._run_via_sidecar(execution, target_list, script_content)
        self.finalize_execution(execution, self.task_name, results)

    def _handle_dangerous_command(self, execution, target_list: list) -> bool:
        check_result = DangerousChecker.check_command(execution.script_content, execution.team)
        if check_result.can_execute:
            return False

        forbidden_rules = [r["rule_name"] for r in check_result.forbidden]
        error_msg = f"检测到高危命令，禁止执行: {', '.join(forbidden_rules)}"
        logger.warning(f"[{self.task_name}] {error_msg}")
        self.update_execution_status(execution, ExecutionStatus.FAILED, finished_at=timezone.now())
        execution.execution_results = [self.build_target_failed_result(t, error_msg) for t in target_list]
        execution.save(update_fields=["execution_results", "updated_at"])
        return True

    def _run_via_ansible_if_needed(self, execution, target_list: list, script_content: str) -> bool:
        if execution.target_source == TargetSource.MANUAL and self._contains_windows_manual_target(target_list):
            if not self._should_use_ansible(execution.target_source, target_list):
                error_msg = "Windows 手动目标仅支持 Ansible/WinRM 执行，请将驱动切换为 Ansible"
                logger.warning(f"[{self.task_name}] {error_msg}")
                self.update_execution_status(execution, ExecutionStatus.FAILED, finished_at=timezone.now())
                execution.execution_results = [self.build_target_failed_result(t, error_msg) for t in target_list]
                execution.save(update_fields=["execution_results", "updated_at"])
                return True
        if not self._should_use_ansible(execution.target_source, target_list):
            return False
        try:
            self._execute_script_via_ansible(execution, target_list, script_content, execution.script_type)
            logger.info(f"[{self.task_name}] Ansible 任务已提交，等待回调: execution_id={self.execution_id}")
            return True
        except Exception as e:
            error_msg = f"Ansible 执行失败: {str(e)}"
            logger.exception(f"[{self.task_name}] {error_msg}")
            self.update_execution_status(execution, ExecutionStatus.FAILED, finished_at=timezone.now())
            execution.execution_results = [self.build_target_failed_result(t, error_msg) for t in target_list]
            execution.save(update_fields=["execution_results", "updated_at"])
            return True

    def _run_via_sidecar(self, execution, target_list: list, script_content: str) -> list:
        results = []
        with ThreadPoolExecutor(max_workers=min(self.MAX_WORKERS, len(target_list))) as pool:
            futures = {
                pool.submit(
                    self.execute_script_on_target,
                    t,
                    execution.target_source,
                    script_content,
                    execution.script_type,
                    execution.timeout,
                ): t
                for t in target_list
            }
            for future in as_completed(futures):
                target_info = futures[future]
                try:
                    result = future.result()
                    results.append(result)
                    logger.info(f"[{self.task_name}] 目标 {target_info.get('name')} 执行完成: status={result['status']}")
                except Exception as e:
                    logger.exception(f"[{self.task_name}] 目标 {target_info.get('name')} 执行异常: {e}")
                    results.append(self.build_target_failed_result(target_info, str(e)))
        return results

    def merge_script_with_params(self, script_content: str, params: str, script_type: str) -> str:
        if not params:
            return script_content

        if script_type == ScriptType.SHELL:
            import shlex

            try:
                tokens = shlex.split(params)
            except ValueError:
                tokens = params.split()

            escaped_params = " ".join(shlex.quote(token) for token in tokens)
            if not escaped_params:
                return script_content
            return f"set -- {escaped_params}\n{script_content}"

        return f"{script_content} {params}"

    def execute_script_on_target(self, target_info: dict, target_source: str, script_content: str, script_type: str, timeout: int) -> dict:
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
            shell = ScriptType.SHELL_MAPPING.get(script_type, "sh")
            if target_source in (TargetSource.NODE_MGMT, TargetSource.SYNC):
                node_id = target_info.get("node_id")
                executor = Executor(node_id)
                exec_result = executor.execute_local(script_content, timeout=timeout, shell=shell)
            else:
                target_id = target_info.get("target_id")
                ssh_creds = self.get_ssh_credentials(target_id)
                if not ssh_creds:
                    raise ValueError(f"无法获取目标凭据: target_id={target_id}")

                executor = Executor(ssh_creds["node_id"])
                exec_result = executor.execute_ssh(
                    command=script_content,
                    host=ssh_creds["host"],
                    username=ssh_creds["username"],
                    password=ssh_creds["password"],
                    private_key=ssh_creds["private_key"],
                    timeout=timeout,
                    port=ssh_creds["port"],
                )

            if isinstance(exec_result, str):
                result["stdout"] = exec_result
                result["stderr"] = ""
                result["exit_code"] = 0
                result["status"] = ExecutionStatus.SUCCESS
            elif isinstance(exec_result, dict):
                result["stdout"] = exec_result.get("stdout", exec_result.get("result", ""))
                result["stderr"] = exec_result.get("stderr", "")
                result["exit_code"] = exec_result.get("exit_code", exec_result.get("code", 0))
                result["status"] = ExecutionStatus.SUCCESS if result["exit_code"] == 0 else ExecutionStatus.FAILED
            else:
                result["stdout"] = str(exec_result)
                result["stderr"] = ""
                result["exit_code"] = 0
                result["status"] = ExecutionStatus.SUCCESS

        except Exception as e:
            result["error_message"] = self.format_error_message(e)
            result["stderr"] = result["error_message"]
            result["status"] = ExecutionStatus.FAILED
            logger.exception(f"目标 {target_name}({target_ip}) 脚本执行失败")

        result["finished_at"] = timezone.now().isoformat()
        return result
