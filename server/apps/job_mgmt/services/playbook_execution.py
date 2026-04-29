import io
import json
import shlex

from asgiref.sync import async_to_sync
from django.utils import timezone

from apps.core.logger import job_logger as logger
from apps.job_mgmt.constants import ExecutionStatus
from apps.job_mgmt.models import Target
from apps.job_mgmt.services import ExecutionTaskBaseService
from apps.node_mgmt.utils.s3 import delete_s3_file, upload_file_to_s3
from apps.rpc.ansible import AnsibleExecutor
from config.components.nats import NATS_NAMESPACE


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

        logger.info(
            f"[{self.task_name}] Playbook信息: "
            f"name={execution.playbook.name}, version={execution.playbook.version}, "
            f"file_key={execution.playbook.file_key}, bucket={execution.playbook.bucket_name}, "
            f"targets={len(target_list)}, target_source={execution.target_source}, "
            f"params='{execution.params}', timeout={execution.timeout}"
        )

        # 判断是否走 Ansible 路径
        if self._should_use_ansible(execution.target_source, target_list):
            logger.info(f"[{self.task_name}] 使用 Ansible 路径执行: execution_id={self.execution_id}")
            self._run_via_ansible(execution, target_list)
        else:
            error_msg = "Playbook 执行仅支持 Ansible 驱动的目标管理主机"
            logger.warning(f"[{self.task_name}] {error_msg}: execution_id={self.execution_id}")
            execution.execution_results = [self.build_target_failed_result(t, error_msg) for t in target_list]
            execution.save(update_fields=["execution_results", "updated_at"])
            self.update_execution_status(execution, ExecutionStatus.FAILED, finished_at=timezone.now())

    def _run_via_ansible(self, execution, target_list: list):
        """通过 AnsibleExecutor.playbook() 执行 Playbook（异步回调）"""
        nats_file_key = None
        try:
            nats_file_key = self._execute_playbook_via_ansible(execution, target_list)
            logger.info(f"[{self.task_name}] Ansible Playbook 任务已提交，等待回调: execution_id={self.execution_id}")
        except Exception as e:
            error_msg = f"Ansible Playbook 执行失败: {str(e)}"
            logger.exception(f"[{self.task_name}] {error_msg}")
            self.update_execution_status(execution, ExecutionStatus.FAILED, finished_at=timezone.now())
            execution.execution_results = [self.build_target_failed_result(t, error_msg) for t in target_list]
            execution.save(update_fields=["execution_results", "updated_at"])
            # 提交失败时立即清理 NATS OS 中转文件
            if nats_file_key:
                try:
                    async_to_sync(delete_s3_file)(nats_file_key)
                    logger.info(f"[{self.task_name}] 已清理 NATS OS 中转文件: {nats_file_key}")
                except Exception as cleanup_err:
                    logger.warning(f"[{self.task_name}] 清理 NATS OS 中转文件失败: {nats_file_key}, error={cleanup_err}")

    @classmethod
    def _execute_playbook_via_ansible(cls, execution, target_list: list) -> str | None:
        """
        通过 Ansible 执行 Playbook（异步方式）

        使用 AnsibleExecutor.playbook()，将 Playbook ZIP 文件信息和主机凭据
        传递给远端 Ansible 执行器，结果通过 NATS 回调返回。

        Returns:
            nats_file_key: 中转到 NATS OS 的文件 key，用于后续清理；无文件时返回 None
        """
        task_name = "execute_playbook_via_ansible"
        playbook = execution.playbook
        nats_file_key = None

        # 获取目标 Target 对象
        target_ids = [t.get("target_id") for t in target_list if t.get("target_id")]
        if not target_ids:
            raise ValueError("未找到有效的目标ID")

        targets = list(Target.objects.filter(id__in=target_ids))
        if not targets:
            raise ValueError("未找到有效的目标记录")

        logger.info(f"[{task_name}] 目标主机: " + ", ".join(f"{t.ip}(id={t.id}, driver={t.driver}, region={t.cloud_region_id})" for t in targets))

        # 按云区域分组，当前仅取第一个云区域
        region_targets = {}
        for target in targets:
            region_id = target.cloud_region_id
            if region_id not in region_targets:
                region_targets[region_id] = []
            region_targets[region_id].append(target)

        if len(region_targets) > 1:
            logger.warning(f"[{task_name}] 检测到多个云区域({list(region_targets.keys())})，当前仅使用第一个云区域执行")

        cloud_region_id = list(region_targets.keys())[0]
        region_target_list = region_targets[cloud_region_id]

        # 获取 Ansible 执行节点
        ansible_node_id = cls._get_ansible_node(cloud_region_id)
        logger.info(f"[{task_name}] Ansible 执行节点: node_id={ansible_node_id}, cloud_region_id={cloud_region_id}")

        # 构建主机凭据
        host_credentials = cls._build_host_credentials(region_target_list)
        logger.info(
            f"[{task_name}] 主机凭据: "
            + ", ".join(f"{c.get('host')}(port={c.get('port')}, user={c.get('user')}, conn={c.get('connection')})" for c in host_credentials)
        )

        # 构建回调配置
        callback_config = {
            "subject": f"{NATS_NAMESPACE}.ansible_task_callback",
            "timeout": 30,
        }

        # 构建 extra_vars（从 execution.params 和 playbook.params 还原）
        extra_vars = cls._build_extra_vars(execution.params, playbook.params)
        logger.info(f"[{task_name}] extra_vars: {extra_vars}")

        # 将 Playbook ZIP 从 MinIO 中转到 NATS JetStream Object Store
        # ansible-executor 只能从 NATS OS 下载文件，而 Playbook 存储在 MinIO 中
        files = []
        if playbook.file:
            nats_file_key = f"job-playbooks/{execution.id}/{playbook.file_name}"
            logger.info(f"[{task_name}] 中转 Playbook ZIP: MinIO({playbook.bucket_name}/{playbook.file_key}) -> NATS OS({nats_file_key})")
            try:
                minio_file = playbook.file
                minio_file.open("rb")
                file_data = minio_file.read()
                minio_file.close()
                logger.info(f"[{task_name}] 从 MinIO 读取成功: size={len(file_data)} bytes")

                # 包装为类文件对象供 upload_file_to_s3 使用
                file_obj = io.BytesIO(file_data)
                file_obj.name = playbook.file_name
                async_to_sync(upload_file_to_s3)(file_obj, nats_file_key)
                logger.info(f"[{task_name}] 上传到 NATS OS 成功: key={nats_file_key}")
            except Exception as e:
                raise ValueError(f"Playbook 文件中转失败: {e}") from e

            files.append(
                {
                    "name": playbook.file_name,
                    "file_key": nats_file_key,
                    "bucket_name": NATS_NAMESPACE,
                }
            )
        logger.info(f"[{task_name}] Playbook 文件: {files}")

        # 调用 AnsibleExecutor.playbook()
        executor = AnsibleExecutor(ansible_node_id)
        logger.info(
            f"[{task_name}] 调用 AnsibleExecutor.playbook(): "
            f"playbook_path=playbook.yml, task_id={execution.id}, timeout={execution.timeout}, "
            f"callback_subject={callback_config['subject']}, "
            f"host_count={len(host_credentials)}, file_count={len(files)}, extra_vars_keys={list(extra_vars.keys())}"
        )
        result = executor.playbook(
            playbook_path="playbook.yml",
            host_credentials=host_credentials,
            files=files,
            extra_vars=extra_vars,
            callback=callback_config,
            task_id=str(execution.id),
            timeout=execution.timeout,
        )

        logger.info(f"[{task_name}] Ansible Playbook 任务已提交: execution_id={execution.id}, result={result}")

        return nats_file_key

    @staticmethod
    def _build_extra_vars(params_str: str, playbook_params: list) -> dict:
        """
        从执行记录的 params 字符串和 Playbook 参数定义还原 extra_vars 字典

        params_str 有两种格式：
        1. JSON 字符串（新格式）：直接 json.loads 还原为 dict
        2. 空格分隔的值字符串（旧格式/脚本模式）：按顺序映射回参数名

        Args:
            params_str: 执行记录的参数字符串
            playbook_params: Playbook 参数定义列表

        Returns:
            dict: {param_name: param_value}
        """
        if not params_str:
            return {}

        # 优先尝试 JSON 解析（新格式）
        try:
            parsed = json.loads(params_str)
            if isinstance(parsed, dict):
                return parsed
        except (json.JSONDecodeError, TypeError):
            pass

        # 旧格式兼容：空格分隔的值字符串，按顺序映射回参数名
        if not playbook_params:
            return {}

        try:
            values = shlex.split(params_str)
        except ValueError:
            values = params_str.split()

        extra_vars = {}
        for i, param_def in enumerate(playbook_params):
            name = param_def.get("name", "")
            if not name:
                continue
            if i < len(values):
                extra_vars[name] = values[i]
            elif param_def.get("default"):
                extra_vars[name] = param_def["default"]

        return extra_vars
