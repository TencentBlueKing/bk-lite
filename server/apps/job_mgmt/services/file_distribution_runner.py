import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from django.utils import timezone

from apps.core.logger import job_logger as logger
from apps.job_mgmt.constants import ExecutionStatus, ExecutorDriver, OSType, TargetSource
from apps.job_mgmt.models import JobExecution, Target
from apps.job_mgmt.services.dangerous_checker import DangerousChecker
from apps.job_mgmt.services.execution_base_service import ExecutionTaskBaseService
from apps.node_mgmt.models import CloudRegion
from apps.rpc.ansible import AnsibleExecutor
from apps.rpc.executor import Executor
from config.components.nats import NATS_NAMESPACE

DEFAULT_RPC_TIMEOUT = int(os.getenv("JOB_MGMT_RPC_TIMEOUT", "60"))
ANSIBLE_TASK_POLL_INTERVAL = 1


class FileDistributionRunner(ExecutionTaskBaseService):
    def __init__(self, execution_id: int):
        super().__init__(execution_id, "distribute_files_task")

    def run(self):
        logger.info(f"[{self.task_name}] 开始执行文件分发任务: execution_id={self.execution_id}")
        execution, target_list = self.prepare_execution()
        if not execution:
            return
        if self._handle_distribution_path_blocked(execution, target_list, self.task_name):
            return

        files = execution.files
        if not files:
            logger.warning(f"[{self.task_name}] 无文件需要分发: execution_id={self.execution_id}")
            self.update_execution_status(execution, ExecutionStatus.SUCCESS, finished_at=timezone.now())
            return

        target_path = execution.target_path
        overwrite = execution.overwrite_strategy == "overwrite"
        results = self.run_distribution_for_targets(execution, target_list, files, target_path, overwrite, self.task_name)
        self.finalize_execution(execution, self.task_name, results)

    def run_distribution_for_targets(
        self,
        execution: JobExecution,
        target_list: list,
        files: list,
        target_path: str,
        overwrite: bool,
        task_name: str,
    ):
        results = []
        with ThreadPoolExecutor(max_workers=min(self.MAX_WORKERS, len(target_list))) as pool:
            futures = {
                pool.submit(self.distribute_file_to_target, t, execution.target_source, files, target_path, execution.timeout, overwrite): t
                for t in target_list
            }
            for future in as_completed(futures):
                target_info = futures[future]
                try:
                    result = future.result()
                    results.append(result)
                    logger.info(f"[{task_name}] 目标 {target_info.get('name')} 分发完成: status={result['status']}")
                except Exception as e:
                    logger.exception(f"[{task_name}] 目标 {target_info.get('name')} 分发异常: {e}")
                    results.append(self.build_target_failed_result(target_info, str(e)))
        return results

    def _handle_distribution_path_blocked(self, execution: JobExecution, target_list: list, task_name: str) -> bool:
        check_result = DangerousChecker.check_path(execution.target_path, execution.team)
        if check_result.can_execute:
            return False

        forbidden_rules = [r["rule_name"] for r in check_result.forbidden]
        error_msg = f"目标路径为高危路径，禁止分发: {', '.join(forbidden_rules)}"
        logger.warning(f"[{task_name}] {error_msg}")
        self.update_execution_status(execution, ExecutionStatus.FAILED, finished_at=timezone.now())
        execution.execution_results = [self.build_target_failed_result(t, error_msg) for t in target_list]
        execution.save(update_fields=["execution_results", "updated_at"])
        return True

    def distribute_file_to_target(
        self,
        target_info: dict,
        target_source: str,
        files: list,
        target_path: str,
        timeout: int,
        overwrite: bool = True,
    ) -> dict:
        result = self._build_distribution_target_result(target_info)
        target_name = result["name"]
        target_ip = result["ip"]

        success = True
        try:
            for file_item in files:
                file_result = {"file_name": file_item.get("name", ""), "success": False, "error": ""}
                file_key = file_item.get("file_key", "")
                file_name = file_item.get("name", "")

                try:
                    if target_source in (TargetSource.NODE_MGMT, TargetSource.SYNC):
                        node_id = target_info.get("node_id")
                        exec_result = self.download_to_local_target(file_key, file_name, target_path, timeout, overwrite, node_id)
                    else:
                        target_id = target_info.get("target_id")
                        if not target_id:
                            raise ValueError("手动目标缺少 target_id")
                        exec_result = self.download_to_manual_target(file_item, target_id, target_path, timeout, overwrite)

                    file_ok, file_error = self.parse_distribution_exec_result(exec_result)
                    file_result["success"] = file_ok
                    file_result["error"] = file_error
                    if not file_ok:
                        success = False

                except Exception as e:
                    file_result["error"] = str(e)
                    success = False
                    logger.exception(f"文件 {file_item.get('name')} 分发到 {target_name} 失败")

                result["file_results"].append(file_result)

        except Exception as e:
            success = False
            result["error_message"] = f"分发异常: {str(e)}"
            logger.exception(f"目标 {target_name}({target_ip}) 文件分发失败")

        self.summarize_distribution_result(result, success, files, target_path)
        return result

    @staticmethod
    def _build_distribution_target_result(target_info: dict) -> dict:
        return {
            "target_key": target_info.get("node_id") or str(target_info.get("target_id", "")),
            "name": target_info.get("name", ""),
            "ip": target_info.get("ip", ""),
            "status": ExecutionStatus.PENDING,
            "stdout": "",
            "stderr": "",
            "exit_code": None,
            "error_message": "",
            "file_results": [],
            "started_at": timezone.now().isoformat(),
            "finished_at": "",
        }

    @staticmethod
    def download_to_local_target(file_key: str, file_name: str, target_path: str, timeout: int, overwrite: bool, node_id: str):
        executor = Executor(node_id)
        return executor.download_to_local(
            bucket_name=NATS_NAMESPACE,
            file_key=file_key,
            file_name=file_name,
            target_path=target_path,
            timeout=timeout,
            overwrite=overwrite,
        )

    @staticmethod
    def _normalize_target_path(target_path: str, os_type: str | None) -> str:
        if os_type != OSType.WINDOWS:
            return target_path
        return str(target_path).replace("\\", "/")

    def download_to_manual_target(self, file_item: dict, target_id: int, target_path: str, timeout: int, overwrite: bool):
        target_obj = Target.objects.filter(id=target_id).first()
        if target_obj and target_obj.os_type == OSType.WINDOWS and target_obj.driver == ExecutorDriver.ANSIBLE:
            normalized_target_path = self._normalize_target_path(target_path, target_obj.os_type)
            return self._download_to_windows_via_ansible(target_obj, [file_item], normalized_target_path, timeout, overwrite)

        if target_obj and target_obj.os_type == OSType.WINDOWS:
            ssh_creds = {
                "host": target_obj.ip,
                "username": target_obj.winrm_user,
                "password": self.decrypt_password(target_obj.winrm_password),
                "private_key": None,
                "port": target_obj.winrm_port,
                "node_id": target_obj.node_id,
            }
        else:
            ssh_creds = self.get_ssh_credentials(target_id)
        if not ssh_creds:
            raise ValueError(f"无法获取目标凭据: target_id={target_id}")

        normalized_target_path = self._normalize_target_path(target_path, target_obj.os_type if target_obj else None)

        if target_obj and target_obj.driver == ExecutorDriver.ANSIBLE:
            if not target_obj.cloud_region_id:
                raise ValueError(f"目标缺少云区域配置: target_id={target_id}")
            instance_id = self.get_cloud_region_name(target_obj.cloud_region_id)
        else:
            instance_id = ssh_creds["node_id"]

        return self.download_to_remote(instance_id, file_item, normalized_target_path, ssh_creds, timeout, overwrite)

    def _download_to_windows_via_ansible(self, target_obj, files: list[dict], target_path: str, timeout: int, overwrite: bool) -> dict:
        if not target_obj.cloud_region_id:
            raise ValueError(f"目标缺少云区域配置: target_id={target_obj.id}")

        ansible_node_id = self._get_ansible_node(target_obj.cloud_region_id)
        executor = AnsibleExecutor(ansible_node_id)
        host_credentials = self._build_host_credentials([target_obj])
        task_id = f"file-dist-{target_obj.id}-{os.urandom(4).hex()}"

        accepted = executor.playbook(
            host_credentials=host_credentials,
            files=files,
            file_distribution={
                "bucket_name": NATS_NAMESPACE,
                "target_path": target_path,
                "overwrite": overwrite,
            },
            task_id=task_id,
            timeout=timeout,
        )
        accepted_task_id = (accepted.get("task_id") if isinstance(accepted, dict) else None) or task_id

        query_timeout = min(timeout, DEFAULT_RPC_TIMEOUT)
        start_time = time.monotonic()
        query_result = None
        poll_attempt = 0
        while True:
            poll_attempt += 1
            elapsed = time.monotonic() - start_time
            query_result = executor.task_query(accepted_task_id, timeout=query_timeout)
            if not isinstance(query_result, dict):
                raise ValueError("Ansible 文件分发返回结果格式非法")

            task_status = query_result.get("status")
            if task_status in {"success", "failed", "callback_failed"}:
                break

            elapsed = time.monotonic() - start_time
            if elapsed >= timeout:
                raise ValueError(f"Ansible 文件分发任务未完成: status={task_status}")

            time.sleep(ANSIBLE_TASK_POLL_INTERVAL)

        if not isinstance(query_result, dict):
            raise ValueError("Ansible 文件分发返回结果格式非法")

        task_status = query_result.get("status")
        if task_status not in {"success", "failed", "callback_failed"}:
            raise ValueError(f"Ansible 文件分发任务未完成: status={task_status}")

        task_result = query_result.get("result", {})
        if not isinstance(task_result, dict):
            raise ValueError("Ansible 文件分发返回结果格式非法")

        host_results = task_result.get("result")
        task_error = str(task_result.get("error") or "")

        if isinstance(host_results, list):
            failed_hosts = [item for item in host_results if isinstance(item, dict) and item.get("status") != "success"]
            error_messages = [str(item.get("error_message") or item.get("stderr") or "") for item in failed_hosts]
            return {
                "success": len(failed_hosts) == 0 and task_result.get("success") is True,
                "result": host_results,
                "error": "\n".join([msg for msg in error_messages if msg]) or task_error,
            }

        return {
            "success": task_result.get("success") is True,
            "result": task_result.get("result", ""),
            "error": task_error,
        }

    @staticmethod
    def get_cloud_region_name(cloud_region_id: int) -> str:
        region = CloudRegion.objects.filter(id=cloud_region_id).first()
        if not region or not region.name:
            raise ValueError(f"云区域 {cloud_region_id} 不存在或名称为空")
        return region.name

    @staticmethod
    def download_to_remote(
        instance_id: str,
        file_item: dict,
        target_path: str,
        ssh_creds: dict,
        timeout: int,
        overwrite: bool,
    ) -> dict:
        has_password = bool(ssh_creds.get("password"))
        has_private_key = bool(ssh_creds.get("private_key"))
        if not has_password and not has_private_key:
            raise ValueError("目标缺少认证信息，需要密码或私钥")

        executor = Executor(instance_id)
        return executor.download_to_remote(
            bucket_name=NATS_NAMESPACE,
            file_key=file_item.get("file_key", ""),
            file_name=file_item.get("name", ""),
            target_path=target_path,
            host=ssh_creds["host"],
            username=ssh_creds["username"],
            password=ssh_creds["password"],
            private_key=ssh_creds["private_key"],
            timeout=timeout,
            port=ssh_creds["port"],
            overwrite=overwrite,
        )

    @staticmethod
    def summarize_distribution_result(result: dict, success: bool, files: list, target_path: str) -> None:
        errors = [f"{fr['file_name']}: {fr['error']}" for fr in result["file_results"] if not fr["success"]]
        error_message = "\n".join(errors) if errors else result.get("error_message", "")
        stdout_message = f"分发 {len(files)} 个文件到 {target_path}"
        if not success and error_message:
            stdout_message = f"NATS接口调用超时: {error_message}" if "RPC request timeout" in error_message else error_message

        result["status"] = ExecutionStatus.SUCCESS if success else ExecutionStatus.FAILED
        result["stdout"] = stdout_message
        result["stderr"] = error_message
        result["exit_code"] = 0 if success else 1
        result["error_message"] = error_message
        result["finished_at"] = timezone.now().isoformat()

    @staticmethod
    def parse_distribution_exec_result(exec_result) -> tuple[bool, str]:
        if isinstance(exec_result, str):
            if "successfully" in exec_result.lower() or "success" in exec_result.lower() or exec_result == "":
                return True, ""
            return False, exec_result

        if isinstance(exec_result, dict):
            success_flag = exec_result.get("success")
            code = exec_result.get("code")
            error_info = exec_result.get("error") or exec_result.get("stderr") or exec_result.get("message")
            result_text = str(exec_result.get("result", "")).lower()
            if success_flag is True:
                return True, ""
            if code is not None and code != 0:
                return False, str(error_info or f"执行失败，code={code}")
            if success_flag is False and error_info:
                return False, str(error_info)
            if "failed" in result_text or "error" in result_text:
                return False, str(exec_result.get("result", "执行失败"))
            return True, ""

        return False, f"未知响应类型: {type(exec_result)}"
