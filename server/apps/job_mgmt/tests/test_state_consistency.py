"""状态一致性修复测试

测试 Issue #2962 和 #2963 的修复：
1. 定时任务与 celery-beat 分离写入的事务保护
2. Ansible 异步回调异常收敛到终态
"""

from unittest.mock import MagicMock, patch

import pytest
from django.utils import timezone

from apps.job_mgmt.constants import ExecutionStatus


@pytest.mark.unit
@pytest.mark.django_db
class TestAnsibleCallbackFailureConvergence:
    """测试 Ansible 回调异常收敛到 FAILED 终态 (Issue #2963)"""

    @pytest.fixture(autouse=True)
    def _mock_terminal_transition(self):
        """本组仅验证解析收敛；CAS 竞争行为由独立回归文件覆盖。"""
        with patch("apps.job_mgmt.nats_api._claim_callback_terminal_state", return_value=True) as claim:
            self.claim_terminal_state = claim
            yield

    def _create_mock_execution(self, task_id=1, status=ExecutionStatus.RUNNING):
        """创建模拟的 JobExecution 对象"""
        execution = MagicMock()
        execution.id = task_id
        execution.status = status
        execution.target_list = [
            {"target_id": "t1", "name": "host1", "ip": "1.2.3.4"},
            {"target_id": "t2", "name": "host2", "ip": "5.6.7.8"},
        ]
        execution.started_at = timezone.now()
        execution.playbook_id = None
        return execution

    def test_invalid_result_format_converges_to_failed(self):
        """测试：结果格式非法时，execution 应收敛到 FAILED"""
        from apps.job_mgmt.nats_api import ansible_task_callback

        mock_execution = self._create_mock_execution()

        with patch("apps.job_mgmt.nats_api.JobExecution.objects.get", return_value=mock_execution), patch(
            "apps.job_mgmt.nats_api.send_callback"
        ) as mock_send_callback, patch("apps.job_mgmt.nats_api.publish_done_sentinel"):
            # 发送非法格式的结果（不是 list）
            result = ansible_task_callback(
                {
                    "task_id": 1,
                    "result": "invalid string result",  # 应该是 list
                }
            )

            # 验证返回失败
            assert result["success"] is False
            assert "已收敛到 FAILED" in result["message"]

            # 验证 execution 状态被设置为 FAILED
            assert mock_execution.status == ExecutionStatus.FAILED
            self.claim_terminal_state.assert_called_once()
            assert not mock_execution.save.called
            assert mock_send_callback.called

    def test_empty_result_converges_to_failed(self):
        """测试：空结果时，execution 应收敛到 FAILED"""
        from apps.job_mgmt.nats_api import ansible_task_callback

        mock_execution = self._create_mock_execution()

        with patch("apps.job_mgmt.nats_api.JobExecution.objects.get", return_value=mock_execution), patch(
            "apps.job_mgmt.nats_api.send_callback"
        ) as mock_send_callback, patch("apps.job_mgmt.nats_api.publish_done_sentinel"):
            # 发送空结果
            result = ansible_task_callback(
                {
                    "task_id": 1,
                    "result": [],  # 空列表
                }
            )

            # 验证返回失败
            assert result["success"] is False
            assert "已收敛到 FAILED" in result["message"]

            # 验证 execution 状态被设置为 FAILED
            assert mock_execution.status == ExecutionStatus.FAILED
            assert mock_send_callback.called

    def test_host_not_matched_converges_to_failed(self):
        """测试：主机未匹配时，execution 应收敛到 FAILED"""
        from apps.job_mgmt.nats_api import ansible_task_callback

        mock_execution = self._create_mock_execution()

        with patch("apps.job_mgmt.nats_api.JobExecution.objects.get", return_value=mock_execution), patch(
            "apps.job_mgmt.nats_api.send_callback"
        ) as mock_send_callback, patch("apps.job_mgmt.nats_api.publish_done_sentinel"):
            # 发送不匹配的主机结果
            result = ansible_task_callback(
                {
                    "task_id": 1,
                    "result": [{"host": "unknown_host", "status": "success", "stdout": "", "stderr": ""}],
                }
            )

            # 验证返回失败
            assert result["success"] is False
            assert "已收敛到 FAILED" in result["message"]

            # 验证 execution 状态被设置为 FAILED
            assert mock_execution.status == ExecutionStatus.FAILED
            assert mock_send_callback.called

    def test_duplicate_host_converges_to_failed(self):
        """测试：主机重复时，execution 应收敛到 FAILED"""
        from apps.job_mgmt.nats_api import ansible_task_callback

        mock_execution = self._create_mock_execution()

        with patch("apps.job_mgmt.nats_api.JobExecution.objects.get", return_value=mock_execution), patch(
            "apps.job_mgmt.nats_api.send_callback"
        ) as mock_send_callback, patch("apps.job_mgmt.nats_api.publish_done_sentinel"):
            # 发送重复主机的结果
            result = ansible_task_callback(
                {
                    "task_id": 1,
                    "result": [
                        {"host": "1.2.3.4", "status": "success", "stdout": "", "stderr": ""},
                        {"host": "1.2.3.4", "status": "success", "stdout": "", "stderr": ""},  # 重复
                    ],
                }
            )

            # 验证返回失败
            assert result["success"] is False
            assert "已收敛到 FAILED" in result["message"]

            # 验证 execution 状态被设置为 FAILED
            assert mock_execution.status == ExecutionStatus.FAILED
            assert mock_send_callback.called

    def test_normal_callback_still_works(self):
        """测试：正常回调仍然正常工作"""
        from apps.job_mgmt.nats_api import ansible_task_callback

        mock_execution = self._create_mock_execution()

        with patch("apps.job_mgmt.nats_api.JobExecution.objects.get", return_value=mock_execution), patch(
            "apps.job_mgmt.nats_api.send_callback"
        ), patch("apps.job_mgmt.nats_api.publish_done_sentinel"):
            # 发送正常的回调结果
            result = ansible_task_callback(
                {
                    "task_id": 1,
                    "result": [
                        {"host": "1.2.3.4", "status": "success", "stdout": "ok", "stderr": ""},
                        {"host": "5.6.7.8", "status": "success", "stdout": "ok", "stderr": ""},
                    ],
                }
            )

            # 验证返回成功
            assert result["success"] is True
            assert result["message"] == "回调处理成功"

            # 验证 execution 状态被设置为 SUCCESS
            assert mock_execution.status == ExecutionStatus.SUCCESS

    def test_terminal_state_is_idempotent(self):
        """测试：已处于终态的任务不会被重复处理"""
        from apps.job_mgmt.nats_api import ansible_task_callback

        mock_execution = self._create_mock_execution(status=ExecutionStatus.SUCCESS)

        with patch("apps.job_mgmt.nats_api.JobExecution.objects.get", return_value=mock_execution):
            result = ansible_task_callback(
                {
                    "task_id": 1,
                    "result": "invalid",  # 即使数据非法也不应处理
                }
            )

            # 验证返回成功（幂等）
            assert result["success"] is True
            assert "任务已处理" in result["message"]

            # 验证 save 没有被调用
            assert not mock_execution.save.called


@pytest.mark.unit
@pytest.mark.django_db
class TestScheduledTaskTransactionProtection:
    """测试定时任务事务保护 (Issue #2962)"""

    def test_create_rolls_back_on_periodic_task_failure(self):
        """测试：PeriodicTask 创建失败时，ScheduledTask 应回滚"""
        from rest_framework import serializers as drf_serializers

        from apps.job_mgmt.serializers.scheduled_task import ScheduledTaskCreateSerializer

        # 模拟请求上下文
        mock_request = MagicMock()
        mock_request.user.username = "testuser"

        # 模拟 ScheduledTaskService.create_periodic_task 返回 None（失败）
        with patch("apps.job_mgmt.serializers.scheduled_task.ScheduledTaskService.create_periodic_task", return_value=None), patch(
            "apps.job_mgmt.serializers.scheduled_task.ScheduledTask.objects.create"
        ) as mock_create:
            mock_instance = MagicMock()
            mock_instance.id = 1
            mock_create.return_value = mock_instance

            serializer = ScheduledTaskCreateSerializer(context={"request": mock_request})

            # 验证抛出 ValidationError
            with pytest.raises(drf_serializers.ValidationError) as exc_info:
                serializer.create(
                    {
                        "name": "test-task",
                        "job_type": "script",
                        "schedule_type": "cron",
                        "cron_expression": "* * * * *",
                    }
                )
            # 验证错误信息
            assert "创建定时调度任务失败" in str(exc_info.value)

    def test_create_succeeds_when_periodic_task_created(self):
        """测试：PeriodicTask 创建成功时，整个流程正常"""
        from apps.job_mgmt.serializers.scheduled_task import ScheduledTaskCreateSerializer

        mock_request = MagicMock()
        mock_request.user.username = "testuser"

        mock_periodic_task = MagicMock()
        mock_periodic_task.id = 100

        with patch("apps.job_mgmt.serializers.scheduled_task.ScheduledTaskService.create_periodic_task", return_value=mock_periodic_task), patch(
            "apps.job_mgmt.serializers.scheduled_task.ScheduledTask.objects.create"
        ) as mock_create:
            mock_instance = MagicMock()
            mock_instance.id = 1
            mock_create.return_value = mock_instance

            serializer = ScheduledTaskCreateSerializer(context={"request": mock_request})
            serializer.create(
                {
                    "name": "test-task",
                    "job_type": "script",
                    "schedule_type": "cron",
                    "cron_expression": "* * * * *",
                }
            )

            # 验证 periodic_task_id 被设置
            assert mock_instance.periodic_task_id == 100
            assert mock_instance.save.called

    def test_update_rolls_back_on_periodic_task_failure_when_enabled(self):
        """测试：启用状态下 PeriodicTask 更新失败时，应回滚"""
        from rest_framework import serializers as drf_serializers

        from apps.job_mgmt.serializers.scheduled_task import ScheduledTaskUpdateSerializer

        mock_request = MagicMock()
        mock_request.user.username = "testuser"

        mock_instance = MagicMock()
        mock_instance.is_enabled = True  # 启用状态

        with patch("apps.job_mgmt.serializers.scheduled_task.ScheduledTaskService.update_periodic_task", return_value=None):
            serializer = ScheduledTaskUpdateSerializer(instance=mock_instance, context={"request": mock_request})

            with pytest.raises(drf_serializers.ValidationError) as exc_info:
                serializer.update(mock_instance, {"name": "updated-name"})

            assert "更新定时调度任务失败" in str(exc_info.value)

    def test_update_succeeds_when_disabled_even_if_periodic_task_fails(self):
        """测试：禁用状态下 PeriodicTask 更新失败时，不应回滚"""
        from apps.job_mgmt.serializers.scheduled_task import ScheduledTaskUpdateSerializer

        mock_request = MagicMock()
        mock_request.user.username = "testuser"

        mock_instance = MagicMock()
        mock_instance.is_enabled = False  # 禁用状态

        with patch("apps.job_mgmt.serializers.scheduled_task.ScheduledTaskService.update_periodic_task", return_value=None):
            serializer = ScheduledTaskUpdateSerializer(instance=mock_instance, context={"request": mock_request})
            result = serializer.update(mock_instance, {"name": "updated-name"})

            # 验证更新成功（禁用状态不需要 PeriodicTask）
            assert result == mock_instance
            assert mock_instance.save.called


@pytest.mark.unit
@pytest.mark.django_db
class TestAnsibleInterpreterSelection:
    """测试 ansible 路径的解释器选择行为"""

    def _build_target(self):
        target = MagicMock()
        target.cloud_region_id = 1
        return target

    def _build_execution(self):
        execution = MagicMock()
        execution.id = 100
        execution.timeout = 60
        return execution

    def test_python_shebang_wraps_script_with_interpreter_command(self):
        from apps.job_mgmt.services.execution_base_service import ExecutionTaskBaseService

        execution = self._build_execution()
        target = self._build_target()

        with patch("apps.job_mgmt.services.execution_base_service.Target.objects.filter", return_value=[target]), patch(
            "apps.job_mgmt.services.execution_base_service.ExecutionTaskBaseService._get_ansible_node", return_value="node-1"
        ), patch(
            "apps.job_mgmt.services.execution_base_service.ExecutionTaskBaseService._build_host_credentials", return_value=[{"host": "10.0.0.1"}]
        ), patch(
            "apps.job_mgmt.services.execution_base_service.AnsibleExecutor"
        ) as mock_executor_cls:
            mock_executor = MagicMock()
            mock_executor.adhoc.return_value = {"accepted": True}
            mock_executor_cls.return_value = mock_executor

            script_content = "#!/usr/bin/env python3\nimport sys\nprint(sys.version)"
            ExecutionTaskBaseService._execute_script_via_ansible(
                execution=execution,
                target_list=[{"target_id": 1}],
                script_content=script_content,
                script_type="shell",
            )

            mock_executor.adhoc.assert_called_once()
            _, kwargs = mock_executor.adhoc.call_args
            assert kwargs["module"] == "shell"
            assert kwargs["module_args"] == "python3 <<'__SCRIPT__'\n#!/usr/bin/env python3\nimport sys\nprint(sys.version)\n__SCRIPT__"
            assert kwargs["extra_vars"] is None

    def test_bash_shebang_uses_ansible_shell_executable(self):
        from apps.job_mgmt.services.execution_base_service import ExecutionTaskBaseService

        execution = self._build_execution()
        target = self._build_target()

        with patch("apps.job_mgmt.services.execution_base_service.Target.objects.filter", return_value=[target]), patch(
            "apps.job_mgmt.services.execution_base_service.ExecutionTaskBaseService._get_ansible_node", return_value="node-1"
        ), patch(
            "apps.job_mgmt.services.execution_base_service.ExecutionTaskBaseService._build_host_credentials", return_value=[{"host": "10.0.0.1"}]
        ), patch(
            "apps.job_mgmt.services.execution_base_service.AnsibleExecutor"
        ) as mock_executor_cls:
            mock_executor = MagicMock()
            mock_executor.adhoc.return_value = {"accepted": True}
            mock_executor_cls.return_value = mock_executor

            script_content = "#!/bin/bash\necho hello"
            ExecutionTaskBaseService._execute_script_via_ansible(
                execution=execution,
                target_list=[{"target_id": 1}],
                script_content=script_content,
                script_type="shell",
            )

            _, kwargs = mock_executor.adhoc.call_args
            assert kwargs["module"] == "shell"
            assert kwargs["module_args"] == script_content
            assert kwargs["extra_vars"] == {"ansible_shell_executable": "/bin/bash"}
