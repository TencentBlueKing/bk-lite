"""周期评估通知的任务快照与投递契约。"""

import pytest
from django.utils import timezone

from apps.patch_mgmt.constants import ComplianceStatus, GovernanceTaskStatus, GovernanceTaskType, OSType
from apps.patch_mgmt.models import (
    AssessmentNotificationDelivery,
    GovernanceTask,
    GovernanceTaskHost,
    HostBaselineBinding,
    PatchBaseline,
    PatchTarget,
    ScanSetting,
)
from apps.patch_mgmt.services.patch_execution_service import finalize_governance_task
from apps.patch_mgmt.tasks import (
    reconcile_assessment_notification_deliveries,
    run_periodic_compliance_scan,
    send_assessment_notification_delivery,
)


@pytest.mark.django_db
def test_periodic_scan_freezes_notification_rules_on_created_task(mocker):
    """周期任务应固化创建时的通知规则，后续设置变更不影响本次任务。"""
    rules = [
        {
            "channel_id": 7,
            "channel_name": "运维邮箱",
            "channel_type": "email",
            "receivers": [11, 12],
            "team_id": 1,
        }
    ]
    setting = ScanSetting.get_singleton()
    setting.is_enabled = True
    setting.notification_enabled = True
    setting.notification_rules = rules
    setting.save()
    target = PatchTarget.objects.create(
        name="host-a",
        ip="10.0.0.1",
        team=[1],
    )
    dispatch = mocker.patch(
        "apps.patch_mgmt.tasks.execute_governance_task.delay"
    )

    run_periodic_compliance_scan()

    task = GovernanceTask.objects.get()
    assert task.target_list == [target.id]
    assert task.trigger_source == "periodic_scan"
    assert task.notification_snapshot == {
        "enabled": True,
        "rules": rules,
    }
    dispatch.assert_called_once_with(task.id)

    setting.notification_rules = []
    setting.save(update_fields=["notification_rules", "updated_at"])
    task.refresh_from_db()
    assert task.notification_snapshot["rules"] == rules


@pytest.mark.django_db
def test_periodic_assessment_terminal_state_creates_one_summary_per_channel():
    """不合规和评估失败应在任务首次进入终态时生成每渠道一条汇总。"""
    targets = [
        PatchTarget.objects.create(name="host-a", ip="10.0.0.1", team=[1]),
        PatchTarget.objects.create(name="host-b", ip="10.0.0.2", team=[1]),
    ]
    baseline = PatchBaseline.objects.create(
        name="Linux 基线",
        os_type=OSType.LINUX,
        team=[1],
    )
    HostBaselineBinding.objects.create(
        target=targets[0],
        baseline=baseline,
        compliance_status=ComplianceStatus.NON_COMPLIANT,
        last_evaluated_at=timezone.now(),
    )
    rules = [
        {
            "channel_id": 7,
            "channel_name": "运维邮箱",
            "channel_type": "email",
            "receivers": [11, 12],
            "team_id": 1,
        },
        {
            "channel_id": 9,
            "channel_name": "自动化工作流",
            "channel_type": "nats",
            "receivers": [],
            "team_id": 1,
        },
    ]
    task = GovernanceTask.objects.create(
        name="周期性合规评估",
        task_type=GovernanceTaskType.ASSESS,
        execution_mode="now",
        status=GovernanceTaskStatus.RUNNING,
        target_list=[target.id for target in targets],
        patch_list=[],
        trigger_source="periodic_scan",
        notification_snapshot={"enabled": True, "rules": rules},
        started_at=timezone.now(),
    )
    GovernanceTaskHost.objects.create(
        task=task,
        target_id=targets[0].id,
        target_name=targets[0].name,
        target_ip=targets[0].ip,
        stage="completed",
    )
    GovernanceTaskHost.objects.create(
        task=task,
        target_id=targets[1].id,
        target_name=targets[1].name,
        target_ip=targets[1].ip,
        stage="failed",
        failed_stage="assess",
    )
    finalize_governance_task(task.id)

    task.refresh_from_db()
    assert task.status == GovernanceTaskStatus.PARTIAL_SUCCESS
    deliveries = list(task.notification_deliveries.order_by("channel_id"))
    assert len(deliveries) == 2
    assert deliveries[0].channel_id == 7
    assert deliveries[0].receivers == [11, 12]
    assert deliveries[1].channel_id == 9
    assert deliveries[1].receivers == []
    assert deliveries[0].summary == {
        "total_count": 2,
        "non_compliant_count": 1,
        "failed_count": 1,
    }
    finalize_governance_task(task.id)
    assert task.notification_deliveries.count() == 2


@pytest.mark.django_db
def test_all_compliant_periodic_assessment_does_not_create_notification():
    """全部合规的周期评估不应生成通知投递。"""
    target = PatchTarget.objects.create(name="host-a", ip="10.0.0.1", team=[1])
    baseline = PatchBaseline.objects.create(
        name="Linux 基线",
        os_type=OSType.LINUX,
        team=[1],
    )
    HostBaselineBinding.objects.create(
        target=target,
        baseline=baseline,
        compliance_status=ComplianceStatus.COMPLIANT,
        last_evaluated_at=timezone.now(),
    )
    task = GovernanceTask.objects.create(
        name="周期性合规评估",
        task_type=GovernanceTaskType.ASSESS,
        status=GovernanceTaskStatus.RUNNING,
        target_list=[target.id],
        patch_list=[],
        trigger_source="periodic_scan",
        notification_snapshot={
            "enabled": True,
            "rules": [
                {
                    "channel_id": 7,
                    "channel_name": "运维邮箱",
                    "channel_type": "email",
                    "receivers": [11],
                    "team_id": 1,
                }
            ],
        },
        started_at=timezone.now(),
    )
    GovernanceTaskHost.objects.create(
        task=task,
        target_id=target.id,
        target_name=target.name,
        target_ip=target.ip,
        stage="completed",
    )

    finalize_governance_task(task.id)

    task.refresh_from_db()
    assert task.status == GovernanceTaskStatus.COMPLETED
    assert task.notification_deliveries.count() == 0
    assert task.notification_reconciled_at is not None


@pytest.mark.django_db
def test_missing_host_result_is_counted_as_assessment_failure():
    """任务异常终止而未落主机结果时，汇总仍应按目标总数计入评估失败。"""
    task = GovernanceTask.objects.create(
        name="周期性合规评估",
        task_type=GovernanceTaskType.ASSESS,
        status=GovernanceTaskStatus.FAILED,
        target_list=[101, 102],
        patch_list=[],
        trigger_source="periodic_scan",
        notification_snapshot={
            "enabled": True,
            "rules": [
                {
                    "channel_id": 7,
                    "channel_name": "运维邮箱",
                    "channel_type": "email",
                    "receivers": [11],
                    "team_id": 1,
                }
            ],
        },
        started_at=timezone.now(),
        finished_at=timezone.now(),
    )

    reconcile_assessment_notification_deliveries()

    delivery = task.notification_deliveries.get()
    assert delivery.summary == {
        "total_count": 2,
        "non_compliant_count": 0,
        "failed_count": 2,
    }


@pytest.mark.django_db
def test_notification_delivery_sends_channel_payload_and_marks_delivered(mocker):
    """投递任务应调用系统管理渠道，成功后持久化投递事实。"""
    task = GovernanceTask.objects.create(
        name="周期性合规评估",
        task_type=GovernanceTaskType.ASSESS,
        status=GovernanceTaskStatus.COMPLETED,
        target_list=[1],
        patch_list=[],
        trigger_source="periodic_scan",
        notification_snapshot={"enabled": True, "rules": []},
        finished_at=timezone.now(),
    )
    delivery = AssessmentNotificationDelivery.objects.create(
        task=task,
        channel_id=9,
        channel_name="自动化工作流",
        channel_type="nats",
        receivers=[],
        team_id=1,
        title="【补丁管理】周期评估发现需关注项",
        content="周期评估已完成。",
        summary={
            "total_count": 1,
            "non_compliant_count": 1,
            "failed_count": 0,
        },
    )
    send = mocker.patch(
        "apps.patch_mgmt.tasks.SystemMgmt.send_msg_with_channel",
        return_value={
            "result": True,
            "code": "delivered",
            "data": {"accepted": True},
        },
    )

    send_assessment_notification_delivery(delivery.id)

    delivery.refresh_from_db()
    assert delivery.status == AssessmentNotificationDelivery.Status.DELIVERED
    assert delivery.attempts == 1
    assert delivery.delivered_at is not None
    assert delivery.last_error == ""
    send.assert_called_once_with(
        channel_id=9,
        title=delivery.title,
        content={
            "message": delivery.content,
            "team": 1,
            "user_ids": [],
        },
        receivers=[],
    )


@pytest.mark.django_db
def test_notification_delivery_failure_retries_with_a_finite_limit(mocker):
    """渠道失败应记录可补偿状态，达到上限后终止，不改变评估结果。"""
    task = GovernanceTask.objects.create(
        name="周期性合规评估",
        task_type=GovernanceTaskType.ASSESS,
        status=GovernanceTaskStatus.COMPLETED,
        target_list=[1],
        patch_list=[],
        trigger_source="periodic_scan",
        finished_at=timezone.now(),
    )
    delivery = AssessmentNotificationDelivery.objects.create(
        task=task,
        channel_id=7,
        channel_name="运维邮箱",
        channel_type="email",
        receivers=[11],
        team_id=1,
        title="【补丁管理】周期评估发现需关注项",
        content="周期评估已完成。",
        summary={"total_count": 1, "non_compliant_count": 1, "failed_count": 0},
        max_attempts=2,
    )
    mocker.patch(
        "apps.patch_mgmt.tasks.SystemMgmt.send_msg_with_channel",
        side_effect=RuntimeError("notification responder unavailable"),
    )

    send_assessment_notification_delivery(delivery.id)

    delivery.refresh_from_db()
    assert delivery.status == AssessmentNotificationDelivery.Status.RETRY
    assert delivery.attempts == 1
    assert delivery.next_retry_at is not None
    assert "notification responder unavailable" in delivery.last_error

    delivery.next_retry_at = timezone.now()
    delivery.save(update_fields=["next_retry_at", "updated_at"])
    send_assessment_notification_delivery(delivery.id)

    delivery.refresh_from_db()
    task.refresh_from_db()
    assert delivery.status == AssessmentNotificationDelivery.Status.FAILED
    assert delivery.attempts == 2
    assert delivery.next_retry_at is None
    assert task.status == GovernanceTaskStatus.COMPLETED


@pytest.mark.django_db
def test_notification_reconciler_recovers_missing_terminal_intent(mocker):
    """任务终态后若首次意图生成中断，运行期对账应幂等恢复。"""
    target = PatchTarget.objects.create(name="host-a", ip="10.0.0.1", team=[1])
    baseline = PatchBaseline.objects.create(
        name="Linux 基线",
        os_type=OSType.LINUX,
        team=[1],
    )
    HostBaselineBinding.objects.create(
        target=target,
        baseline=baseline,
        compliance_status=ComplianceStatus.NON_COMPLIANT,
        last_evaluated_at=timezone.now(),
    )
    task = GovernanceTask.objects.create(
        name="周期性合规评估",
        task_type=GovernanceTaskType.ASSESS,
        status=GovernanceTaskStatus.COMPLETED,
        target_list=[target.id],
        patch_list=[],
        trigger_source="periodic_scan",
        notification_snapshot={
            "enabled": True,
            "rules": [
                {
                    "channel_id": 7,
                    "channel_name": "运维邮箱",
                    "channel_type": "email",
                    "receivers": [11],
                    "team_id": 1,
                }
            ],
        },
        started_at=timezone.now(),
        finished_at=timezone.now(),
    )
    GovernanceTaskHost.objects.create(
        task=task,
        target_id=target.id,
        target_name=target.name,
        target_ip=target.ip,
        stage="completed",
    )
    dispatch = mocker.patch(
        "apps.patch_mgmt.tasks.send_assessment_notification_delivery.delay"
    )

    reconcile_assessment_notification_deliveries()

    task.refresh_from_db()
    delivery = task.notification_deliveries.get()
    assert task.notification_reconciled_at is not None
    assert delivery.status == AssessmentNotificationDelivery.Status.PENDING
    dispatch.assert_called_once_with(delivery.id)
