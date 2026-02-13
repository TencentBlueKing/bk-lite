"""策略实例基准服务 - 管理 PolicyInstanceBaseline 的创建、同步和清理"""

from datetime import datetime, timezone

from apps.core.logger import monitor_logger as logger
from apps.monitor.models import (
    MonitorInstance,
    MonitorInstanceOrganization,
    PolicyInstanceBaseline,
)


class PolicyBaselineService:
    """策略实例基准服务

    负责管理策略监控的维度组合基准数据，用于无数据检测。

    Methods:
        refresh(): 全量刷新 - 查询VM获取当前维度组合，删除旧基准，插入新基准
        sync(metric_instances): 增量同步 - 仅添加新的基准，不删除已有基准
        clear(): 清空 - 删除该策略的所有基准
    """

    def __init__(self, policy):
        """初始化服务

        Args:
            policy: MonitorPolicy 对象
        """
        self.policy = policy

    def refresh(self):
        """全量刷新基准数据

        查询 VictoriaMetrics 获取当前所有维度组合，删除旧基准后插入新基准。
        用于：策略创建/修改启用无数据告警、用户关闭无数据告警时选择更新基准。
        """
        if not self.policy.source:
            logger.info(f"Policy {self.policy.id} has no source, skip baseline refresh")
            return

        instances_map = self._build_instances_map()
        if not instances_map:
            logger.warning(
                f"Policy {self.policy.id} has no instances, clearing baselines"
            )
            self.clear()
            return

        metric_instances = self._query_metric_instances(instances_map)
        if not metric_instances:
            logger.info(
                f"Policy {self.policy.id} has no metric data, clearing baselines"
            )
            self.clear()
            return

        self._replace_baselines(metric_instances)
        logger.info(
            f"Policy {self.policy.id}: refreshed {len(metric_instances)} baselines"
        )

    def sync(self, metric_instances: dict[str, str]):
        """增量同步基准数据

        仅添加新的基准，不删除已有基准。
        用于：扫描过程中检测到新的维度组合。

        Args:
            metric_instances: {metric_instance_id: monitor_instance_id} 映射
        """
        if not self.policy.source or not metric_instances:
            return

        existing_baselines = set(
            PolicyInstanceBaseline.objects.filter(policy_id=self.policy.id).values_list(
                "metric_instance_id", flat=True
            )
        )

        new_baselines = []
        for metric_instance_id, monitor_instance_id in metric_instances.items():
            if metric_instance_id not in existing_baselines:
                new_baselines.append(
                    PolicyInstanceBaseline(
                        policy_id=self.policy.id,
                        monitor_instance_id=monitor_instance_id,
                        metric_instance_id=metric_instance_id,
                    )
                )

        if new_baselines:
            PolicyInstanceBaseline.objects.bulk_create(
                new_baselines, ignore_conflicts=True
            )
            logger.info(
                f"Policy {self.policy.id}: synced {len(new_baselines)} new baselines"
            )

    def clear(self):
        """清空该策略的所有基准数据

        用于：策略修改禁用无数据告警。
        """
        deleted_count, _ = PolicyInstanceBaseline.objects.filter(
            policy_id=self.policy.id
        ).delete()
        if deleted_count > 0:
            logger.info(f"Policy {self.policy.id}: cleared {deleted_count} baselines")

    def _build_instances_map(self) -> dict[str, str]:
        """构建策略适用的实例映射

        Returns:
            dict: {monitor_instance_id: monitor_instance_name}
        """
        if not self.policy.source:
            return {}

        source_type = self.policy.source["type"]
        source_values = self.policy.source["values"]

        instance_list = self._get_instance_list_by_source(source_type, source_values)

        instances = MonitorInstance.objects.filter(
            monitor_object_id=self.policy.monitor_object_id,
            id__in=instance_list,
            is_deleted=False,
        )
        return {instance.id: instance.name for instance in instances}

    def _get_instance_list_by_source(
        self, source_type: str, source_values: list
    ) -> list:
        """根据来源类型获取实例列表"""
        if source_type == "instance":
            return source_values

        if source_type == "organization":
            return list(
                MonitorInstanceOrganization.objects.filter(
                    monitor_instance__monitor_object_id=self.policy.monitor_object_id,
                    organization__in=source_values,
                ).values_list("monitor_instance_id", flat=True)
            )

        return []

    def _query_metric_instances(self, instances_map: dict[str, str]) -> dict[str, str]:
        """查询 VictoriaMetrics 获取当前维度组合

        Args:
            instances_map: {monitor_instance_id: monitor_instance_name}

        Returns:
            dict: {metric_instance_id: monitor_instance_id}
        """
        if not self.policy.last_run_time:
            self.policy.last_run_time = datetime.now(timezone.utc)

        try:
            # Lazy import to avoid circular dependency
            from apps.monitor.tasks.services.policy_scan.metric_query import (
                MetricQueryService,
            )

            metric_query_service = MetricQueryService(self.policy, instances_map)
            metric_query_service.set_monitor_obj_instance_key()

            metrics = metric_query_service.query_aggregation_metrics(self.policy.period)

            result = {}
            group_by_keys = self.policy.group_by or []

            for metric_info in metrics.get("data", {}).get("result", []):
                instance_id_tuple = tuple(
                    [metric_info["metric"].get(key) for key in group_by_keys]
                )
                metric_instance_id = str(instance_id_tuple)
                monitor_instance_id = (
                    str((instance_id_tuple[0],)) if instance_id_tuple else ""
                )

                if monitor_instance_id in instances_map:
                    result[metric_instance_id] = monitor_instance_id

            return result

        except Exception as e:
            logger.error(
                f"Policy {self.policy.id}: failed to query metric instances: {e}",
                exc_info=True,
            )
            return {}

    def _replace_baselines(self, metric_instances: dict[str, str]):
        """全量替换基准数据

        Args:
            metric_instances: {metric_instance_id: monitor_instance_id}
        """
        PolicyInstanceBaseline.objects.filter(policy_id=self.policy.id).delete()

        new_baselines = [
            PolicyInstanceBaseline(
                policy_id=self.policy.id,
                monitor_instance_id=monitor_instance_id,
                metric_instance_id=metric_instance_id,
            )
            for metric_instance_id, monitor_instance_id in metric_instances.items()
        ]

        if new_baselines:
            PolicyInstanceBaseline.objects.bulk_create(new_baselines)
