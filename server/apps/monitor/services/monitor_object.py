import hashlib
import re
import time
import uuid

from django.db import transaction
from django.db.models import Q
from django.db.models.fields.json import KeyTextTransform

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.core.logger import monitor_logger as logger
from apps.core.models.maintainer_info import maintainer_kwargs
from apps.core.utils.current_team_scope import _normalize_organization_ids
from apps.monitor.constants.database import DatabaseConstants
from apps.monitor.constants.monitor_object import MonitorObjConstants
from apps.monitor.models.collect_config import CollectConfig
from apps.monitor.models.monitor_metrics import Metric
from apps.monitor.models.monitor_object import MonitorInstance, MonitorInstanceOrganization, MonitorObject, MonitorObjectType
from apps.monitor.models.plugin import MonitorPlugin
from apps.monitor.services.host_container_asset_ip import fill_missing_host_container_asset_ips
from apps.monitor.tasks.grouping_rule import sync_instance_and_group
from apps.monitor.utils.dimension import parse_instance_id
from apps.monitor.utils.display_fields_metrics import display_field_key, extract_field_bindings, extract_metric_bindings
from apps.monitor.utils.instance import list_reporting_status
from apps.monitor.utils.last_sample import LAST_SAMPLE_LOOKBACK, last_sample_timestamp_query, last_sample_unix_seconds
from apps.monitor.utils.victoriametrics_api import VictoriaMetricsAPI
from apps.monitor.utils.vm_query_batch import run_unique_vm_queries

# 实例 status 映射短 TTL 缓存，缓解列表/轮询重复打 VM。
_INSTANCE_STATUS_CACHE_TTL_SECONDS = 15.0
_INSTANCE_STATUS_CACHE_MAX = 128
_instance_status_cache: dict[str, tuple[float, dict]] = {}
# status 查询硬上限，避免无界 series 打爆 VM；已带 topk/bottomk/limitk 的查询不改写。
STATUS_QUERY_MAX_SERIES = 10000


class MonitorObjectService:
    @staticmethod
    def _project_instance_identity(qs):
        return qs.only(
            "id",
            "name",
            "interval",
            "cloud_region_id",
            "ip",
            "summary_facts",
            "fallback_sampling_rate",
            "node_id",
            "cmdb_id",
        )

    @staticmethod
    def validate_new_instance_name_unique(monitor_object_id, monitor_instance_name):
        if not monitor_instance_name:
            return
        exists = MonitorInstance.objects.filter(
            monitor_object_id=monitor_object_id,
            name=monitor_instance_name,
            is_deleted=False,
        ).exists()
        if exists:
            raise BaseAppException("实例名称已存在")

    @staticmethod
    def validate_update_instance_name_unique(instance, monitor_instance_name):
        if not monitor_instance_name or instance.name == monitor_instance_name:
            return
        exists = (
            MonitorInstance.objects.filter(
                monitor_object_id=instance.monitor_object_id,
                name=monitor_instance_name,
                is_deleted=False,
            )
            .exclude(id=instance.id)
            .exists()
        )
        if exists:
            raise BaseAppException("实例名称已存在")

    @staticmethod
    def clear_instance_status_cache() -> None:
        _instance_status_cache.clear()

    @staticmethod
    def get_instances_by_metric(metric: str, instance_id_keys: list):
        """获取监控对象实例"""
        if not metric:
            return {}

        cache_key = hashlib.md5(f"{metric}|{','.join(instance_id_keys or [])}".encode("utf-8")).hexdigest()
        now = time.monotonic()
        cached = _instance_status_cache.get(cache_key)
        if cached and now - cached[0] < _INSTANCE_STATUS_CACHE_TTL_SECONDS:
            return cached[1]

        from apps.monitor.services.metrics import Metrics

        query = last_sample_timestamp_query(metric)
        if not Metrics.query_already_limited(query):
            query = f"limitk({STATUS_QUERY_MAX_SERIES}, {query})"

        metrics = VictoriaMetricsAPI().query(query, step=LAST_SAMPLE_LOOKBACK)
        instance_map = {}
        for metric_info in metrics.get("data", {}).get("result", []):
            instance_id = str(tuple(metric_info["metric"].get(i) for i in instance_id_keys))
            if not instance_id:
                continue
            _time = last_sample_unix_seconds(metric_info)
            if _time is None:
                continue
            agent_id = metric_info.get("metric", {}).get("agent_id")

            if instance_id not in instance_map:
                instance_map[instance_id] = {
                    "instance_id": instance_id,
                    "agent_id": agent_id,
                    "time": _time,
                }
            else:
                if _time > instance_map[instance_id]["time"]:
                    instance_map[instance_id] = {
                        "instance_id": instance_id,
                        "agent_id": agent_id,
                        "time": _time,
                    }

        if len(_instance_status_cache) >= _INSTANCE_STATUS_CACHE_MAX:
            _instance_status_cache.clear()
        _instance_status_cache[cache_key] = (now, instance_map)
        return instance_map

    @staticmethod
    def _safe_get_instances_by_metric(metric: str, instance_id_keys: list):
        """状态存储不可用时保留数据库实例，并将实时状态降级为不可用。"""
        try:
            return MonitorObjectService.get_instances_by_metric(metric, instance_id_keys)
        except Exception:
            logger.exception("查询监控实例实时状态失败，列表将保留数据库实例并标记为不可用")
            return {}

    @staticmethod
    def _safe_fill_display_metrics(monitor_object_id, obj_metric_map, result):
        """展示指标不可用不应阻断实例身份与基础事实列表。"""
        try:
            MonitorObjectService._fill_display_metrics(monitor_object_id, obj_metric_map, result)
        except Exception:
            logger.exception("回填监控实例展示指标失败，列表将保留基础事实")

    @staticmethod
    def _filter_visible_organizations(queryset, visible_organization_ids):
        if visible_organization_ids is None:
            return queryset
        try:
            visible_organization_ids = _normalize_organization_ids(visible_organization_ids)
        except BaseAppException:
            return queryset.none()
        return queryset.filter(organization__in=visible_organization_ids)

    @staticmethod
    def add_attr(items: list, visible_organization_ids=None):
        # 状态计算, 补充组织
        org_objs = MonitorInstanceOrganization.objects.filter(monitor_instance_id__in=[i["instance_id"] for i in items])
        org_objs = MonitorObjectService._filter_visible_organizations(org_objs, visible_organization_ids)
        org_map = {}
        for org in org_objs:
            if org.monitor_instance_id not in org_map:
                org_map[org.monitor_instance_id] = set()
            org_map[org.monitor_instance_id].add(org.organization)

        for conf_info in items:
            organizations = list(org_map.get(conf_info["instance_id"], []))
            conf_info["organizations"] = organizations
            conf_info["organization"] = organizations

            if conf_info["time"]:
                conf_info["status"] = list_reporting_status(conf_info["time"])
            else:
                conf_info["status"] = "unavailable"

    @staticmethod
    def get_monitor_instance(
        monitor_object_id,
        page,
        page_size,
        name,
        qs,
        add_metrics=False,
        monitor_plugin_id=None,
        visible_organization_ids=None,
        vm_params=None,
        instance_id=None,
    ):
        """获取监控对象实例"""
        qs = qs.filter(
            monitor_object_id=monitor_object_id,
            is_deleted=False,
            is_active=True,
        )
        # 可选精确主键过滤（存储键形态，如 "('h1',)"）；与 name 模糊互不干扰。
        if instance_id:
            qs = qs.filter(id=instance_id)
        if name:
            # 与列表「IP信息」/ ${resource_ip} 同源：summary_facts['asset.ip'] 优先字段。
            qs = qs.annotate(_asset_ip_fact=KeyTextTransform("asset.ip", "summary_facts")).filter(
                Q(name__icontains=name) | Q(ip__icontains=name) | Q(_asset_ip_fact__icontains=name)
            )

        monitor_obj = MonitorObject.objects.filter(id=monitor_object_id).first()
        if not monitor_obj:
            raise BaseAppException("Monitor object does not exist")
        monitor_objs = MonitorObject.objects.all().values(*MonitorObjConstants.OBJ_KEYS)
        obj_metric_map = {i["name"]: i for i in monitor_objs}
        obj_metric_map = obj_metric_map.get(monitor_obj.name)
        if not obj_metric_map:
            raise BaseAppException("Monitor object default metric does not exist")

        # Process 主机 / asset.ip / Enum 指标过滤在 list 与 search 共用同一套规则。
        from apps.monitor.services.monitor_instance import InstanceSearch

        qs = InstanceSearch.apply_process_instance_filters(
            qs,
            monitor_obj.name,
            vm_params,
            monitor_object_id=monitor_obj.id,
        )

        status_query = obj_metric_map.get("default_metric", "")
        if monitor_plugin_id:
            plugin = (
                MonitorPlugin.objects.filter(
                    id=monitor_plugin_id,
                    monitor_object=monitor_object_id,
                )
                .only("id", "status_query")
                .first()
            )
            if not plugin:
                return {"count": 0, "results": []}
            if plugin.status_query:
                status_query = plugin.status_query

        instance_map = MonitorObjectService._safe_get_instances_by_metric(
            status_query,
            obj_metric_map.get("instance_id_keys"),
        )
        if monitor_plugin_id:
            qs = qs.filter(id__in=instance_map.keys())

        status_raw = None
        if isinstance(vm_params, dict):
            status_raw = vm_params.get("status")
        qs = InstanceSearch.apply_status_filter_to_qs(qs, instance_map, status_raw)

        # 去除重复
        qs = qs.distinct()

        count = qs.count()

        start = (page - 1) * page_size
        end = start + page_size
        projected_qs = MonitorObjectService._project_instance_identity(qs)
        if page_size == -1:
            objs = projected_qs
        else:
            objs = projected_qs[start:end]
        org_objs = MonitorInstanceOrganization.objects.filter(monitor_instance_id__in=[obj.id for obj in objs])
        org_objs = MonitorObjectService._filter_visible_organizations(org_objs, visible_organization_ids)
        org_map = {}
        for org in org_objs:
            if org.monitor_instance_id not in org_map:
                org_map[org.monitor_instance_id] = set()
            org_map[org.monitor_instance_id].add(org.organization)

        result = []

        for obj in objs:
            result.append(MonitorObjectService._serialize_instance_list_item(obj, instance_map, org_map))
        fill_missing_host_container_asset_ips(result, monitor_obj.name)

        if add_metrics and page_size != -1:
            MonitorObjectService._safe_fill_display_metrics(monitor_object_id, obj_metric_map, result)

        MonitorObjectService.add_attr(result, visible_organization_ids)

        return dict(count=count, results=result)

    @staticmethod
    def _query_metric_values(metric_obj, target_instances):
        """对 target_instances 跑该指标的 VM 查询,返回 {instance_id: value}。"""
        target_ids = [parse_instance_id(inst["instance_id"]) for inst in target_instances]
        query_parts = []
        for i, key in enumerate(metric_obj.instance_id_keys):
            values_set = {re.escape(str(item[i])) for item in target_ids if len(item) > i and item[i] is not None}
            if not values_set:
                continue
            # re.escape 的反斜杠需再做一次 PromQL 字符串转义,否则 VM 侧报 invalid syntax
            values = MonitorObjectService._escape_promql_label_value("|".join(sorted(values_set)))
            query_parts.append(f'{key}=~"{values}"')

        query = metric_obj.query.replace("__$labels__", f"{', '.join(query_parts)}")
        vm_api = VictoriaMetricsAPI()
        metrics = vm_api.query(query)
        metric_results = metrics.get("data", {}).get("result", [])
        timestamp_map = MonitorObjectService._query_enum_metric_sample_timestamps(vm_api, query, metric_obj, metric_results)
        selected_map = {}
        for metric in metric_results:
            instance_id = str(tuple(metric["metric"].get(i) for i in metric_obj.instance_id_keys))
            value = metric["value"][1]
            sample_time = timestamp_map.get((instance_id, MonitorObjectService._vm_metric_signature(metric)))
            if MonitorObjectService._should_replace_display_metric_value(selected_map.get(instance_id), value, sample_time):
                selected_map[instance_id] = {"value": value, "sample_time": sample_time}
        return {instance_id: item["value"] for instance_id, item in selected_map.items()}

    @staticmethod
    def _query_enum_metric_sample_timestamps(vm_api, query, metric_obj, metric_results):
        if (getattr(metric_obj, "data_type", "") or "").lower() != "enum":
            return {}
        instance_counts = {}
        for metric in metric_results:
            instance_id = str(tuple(metric["metric"].get(i) for i in metric_obj.instance_id_keys))
            instance_counts[instance_id] = instance_counts.get(instance_id, 0) + 1
        if not any(count > 1 for count in instance_counts.values()):
            return {}

        timestamp_metrics = vm_api.query(f"timestamp({query})")
        timestamp_map = {}
        for metric in timestamp_metrics.get("data", {}).get("result", []):
            instance_id = str(tuple(metric["metric"].get(i) for i in metric_obj.instance_id_keys))
            try:
                timestamp = float(metric["value"][1])
            except (IndexError, TypeError, ValueError):
                continue
            timestamp_map[(instance_id, MonitorObjectService._vm_metric_signature(metric))] = timestamp
        return timestamp_map

    @staticmethod
    def _vm_metric_signature(metric):
        return tuple(sorted((key, value) for key, value in metric.get("metric", {}).items() if key != "__name__"))

    @staticmethod
    def _should_replace_display_metric_value(current, new_value, new_sample_time):
        if current is None:
            return True
        current_sample_time = current.get("sample_time")
        if new_sample_time is not None or current_sample_time is not None:
            if current_sample_time is None:
                return True
            if new_sample_time is None:
                return False
            if new_sample_time != current_sample_time:
                return new_sample_time > current_sample_time

        try:
            return float(new_value) > float(current["value"])
        except (ValueError, TypeError):
            return False

    @staticmethod
    def _build_field_query(metric_obj, labels_str):
        """按实例标签过滤条件拼出字段展示列的取数查询。"""
        query_template = (getattr(metric_obj, "query", "") or "").strip()
        if "__$labels__" in query_template:
            return query_template.replace("__$labels__", labels_str)
        metric_name = (getattr(metric_obj, "name", "") or "").strip()
        if metric_name:
            return f"{metric_name}{{{labels_str}}}" if labels_str else metric_name
        return query_template

    @staticmethod
    def query_field_label_values(metric_obj, field):
        """查询该指标全部 series 的 label 取值,返回 {instance_id: field_value}(同实例取最新样本)。

        与 ``_query_metric_field_values`` 的区别是不限定目标实例,供字段展示列的筛选取值与
        候选项收集复用。
        """
        metrics = VictoriaMetricsAPI().query(MonitorObjectService._build_field_query(metric_obj, ""))
        value_map = {}
        time_map = {}
        for metric in metrics.get("data", {}).get("result", []):
            labels = metric.get("metric", {})
            field_value = labels.get(field)
            if field_value in (None, ""):
                continue
            parts = [labels.get(key) for key in metric_obj.instance_id_keys]
            if any(part in (None, "") for part in parts):
                continue
            instance_id = str(tuple(str(part) for part in parts))
            timestamp = metric.get("value", [0])[0]
            if instance_id not in value_map or timestamp >= time_map.get(instance_id, 0):
                value_map[instance_id] = field_value
                time_map[instance_id] = timestamp
        return value_map

    @staticmethod
    def _query_metric_field_values(metric_obj, target_instances, field):
        """对 target_instances 查询指标,返回 VM label 字段值 {instance_id: field_value}。"""
        target_ids = [parse_instance_id(inst["instance_id"]) for inst in target_instances]
        query_parts = []
        for i, key in enumerate(metric_obj.instance_id_keys):
            values_set = {re.escape(str(item[i])) for item in target_ids if len(item) > i and item[i] is not None}
            if not values_set:
                continue
            values = MonitorObjectService._escape_promql_label_value("|".join(sorted(values_set)))
            query_parts.append(f'{key}=~"{values}"')

        labels_str = f"{', '.join(query_parts)}"
        query = MonitorObjectService._build_field_query(metric_obj, labels_str)
        metrics = VictoriaMetricsAPI().query(query)
        target_instance_ids = {inst["instance_id"] for inst in target_instances}
        value_map = {}
        time_map = {}
        for metric in metrics.get("data", {}).get("result", []):
            labels = metric.get("metric", {})
            field_value = labels.get(field)
            if field_value in (None, ""):
                continue
            label_values = tuple(labels.get(i) for i in metric_obj.instance_id_keys)
            instance_id = str(label_values)
            if instance_id not in target_instance_ids:
                for value in label_values:
                    value_str = str(value)
                    if value_str in target_instance_ids:
                        instance_id = value_str
                        break
                    parsed_key = str(parse_instance_id(value_str))
                    if parsed_key in target_instance_ids:
                        instance_id = parsed_key
                        break
            timestamp = metric.get("value", [0])[0]
            if instance_id not in value_map or timestamp >= time_map.get(instance_id, 0):
                value_map[instance_id] = field_value
                time_map[instance_id] = timestamp
        return value_map

    @staticmethod
    def _merge_reported_plugin_coverage(monitor_object_id, result, instance_plugin_map):
        """把无 CollectConfig 但已上报的实例并入插件归属，供展示列隔离使用。"""
        uncovered = [inst for inst in result if inst["instance_id"] not in instance_plugin_map]
        if not uncovered:
            return

        plugin_status_qs = (
            MonitorPlugin.objects.filter(monitor_object=monitor_object_id).exclude(status_query="").values_list("name", "status_query").distinct()
        )
        plugin_queries = []
        for plugin_name, status_query in plugin_status_qs:
            query = (status_query or "").strip()
            if not query:
                continue
            plugin_queries.append((plugin_name, query))

        vm_api = VictoriaMetricsAPI()
        responses, errors = run_unique_vm_queries(
            (query for _, query in plugin_queries),
            vm_api.query,
        )
        for plugin_name, query in plugin_queries:
            if query in errors:
                error = errors[query]
                logger.warning(
                    "回填展示列时查询插件上报状态失败: plugin=%s",
                    plugin_name,
                    exc_info=(type(error), error, error.__traceback__),
                )
                continue
            resp = responses[query]
            reported_primary_ids = {metric["metric"].get("instance_id") for metric in resp.get("data", {}).get("result", [])}
            reported_primary_ids.discard(None)
            if not reported_primary_ids:
                continue
            for inst in uncovered:
                parsed = parse_instance_id(inst["instance_id"])
                primary = str(parsed[0]) if parsed else None
                if primary in reported_primary_ids:
                    instance_plugin_map.setdefault(inst["instance_id"], set()).add(plugin_name)

    @staticmethod
    def _fill_display_metrics(monitor_object_id, obj_metric_map, result):
        """按 display_fields 的 (plugin, metric) 绑定回填展示指标值。

        - 回填 key 用复合 key ``<plugin>::<metric>``(见 display_field_key),避免不同插件的同名
          指标互相覆盖;
        - 按插件(模板)隔离:只把“采集配置归属该插件”的实例纳入该绑定取数,别的插件的实例该列留空。
          无采集配置的实例无法判定插件归属,不展示带插件的绑定指标(显示 --)。
        - 兼容:绑定缺 plugin(遗留配置)时按指标名匹配、不做隔离、用裸指标名回填;display_fields
          为空时退回 supplementary_indicators(裸指标名,不区分插件)。
        """
        display_fields = obj_metric_map.get("display_fields", [])
        bindings = extract_metric_bindings(display_fields)
        field_bindings = extract_field_bindings(display_fields)

        if not bindings and not field_bindings:
            supplementary = obj_metric_map.get("supplementary_indicators", [])
            if not supplementary:
                return
            for metric_obj in Metric.objects.filter(monitor_object_id=monitor_object_id, name__in=supplementary):
                value_map = MonitorObjectService._query_metric_values(metric_obj, result)
                for instance in result:
                    instance[metric_obj.name] = value_map.get(instance["instance_id"])
            return

        # 实例 -> 其采集配置覆盖的插件名集合(用于按插件隔离)
        instance_plugin_map = {}
        cc_qs = CollectConfig.objects.filter(
            monitor_instance_id__in=[inst["instance_id"] for inst in result],
            monitor_plugin__isnull=False,
        ).values_list("monitor_instance_id", "monitor_plugin__name")
        for inst_id, plugin_name in cc_qs:
            instance_plugin_map.setdefault(inst_id, set()).add(plugin_name)

        # 派生/上报型实例(如 K8s 集群/Pod/Node 经集群内采集器上报,但 bk-lite 侧无 CollectConfig)
        # 也应纳入其「上报插件」的展示列取数;否则插件隔离会把它们一律判为 --。
        MonitorObjectService._merge_reported_plugin_coverage(monitor_object_id, result, instance_plugin_map)

        # 同名指标可能分属多个插件,按 (plugin, name) 精确取;另留 name 兜底给遗留无 plugin 的绑定
        metric_by_plugin = {}
        metric_by_name = {}
        for metric_obj in Metric.objects.filter(
            monitor_object_id=monitor_object_id,
            name__in=[b["metric"] for b in bindings + field_bindings],
        ).select_related("monitor_plugin"):
            plugin_name = metric_obj.monitor_plugin.name if metric_obj.monitor_plugin_id else ""
            metric_by_plugin[(plugin_name, metric_obj.name)] = metric_obj
            metric_by_name.setdefault(metric_obj.name, metric_obj)

        # 先把每个绑定解析成 (plugin, metric, metric_obj, eligible)
        resolved = []
        for binding in bindings:
            plugin_name, metric_name = binding["plugin"], binding["metric"]
            if plugin_name:
                metric_obj = metric_by_plugin.get((plugin_name, metric_name))
                eligible = [inst for inst in result if plugin_name in instance_plugin_map.get(inst["instance_id"], set())]
            else:
                # 遗留绑定无 plugin:按名取任一插件、不隔离,保持旧行为
                metric_obj = metric_by_name.get(metric_name)
                eligible = result
            if not metric_obj or not eligible:
                continue
            resolved.append((plugin_name, metric_name, metric_obj, eligible))

        # 按「查询模板 + instance_id_keys」分组合并:同名指标(各品牌 query 相同)只发一次 VM 查询,
        # 覆盖该组所有 eligible 实例,再按各绑定的插件分发回各自实例,避免 N 个品牌 = N 次串行查询。
        groups = {}
        for item in resolved:
            metric_obj = item[2]
            group_key = (metric_obj.query, tuple(metric_obj.instance_id_keys))
            groups.setdefault(group_key, []).append(item)

        for items in groups.values():
            union = {}
            for _, _, _, eligible in items:
                for inst in eligible:
                    union[inst["instance_id"]] = inst
            value_map = MonitorObjectService._query_metric_values(items[0][2], list(union.values()))
            for plugin_name, metric_name, _, eligible in items:
                out_key = display_field_key(plugin_name, metric_name)
                for instance in eligible:
                    instance[out_key] = value_map.get(instance["instance_id"])

        for binding in field_bindings:
            plugin_name, metric_name, field = binding["plugin"], binding["metric"], binding["field"]
            if plugin_name:
                metric_obj = metric_by_plugin.get((plugin_name, metric_name))
                eligible = [inst for inst in result if plugin_name in instance_plugin_map.get(inst["instance_id"], set())]
            else:
                metric_obj = metric_by_name.get(metric_name)
                eligible = result
            if not metric_obj or not eligible:
                continue
            value_map = MonitorObjectService._query_metric_field_values(metric_obj, eligible, field)
            out_key = display_field_key(plugin_name, metric_name, field)
            for instance in eligible:
                instance[out_key] = value_map.get(instance["instance_id"])

    @staticmethod
    def _serialize_instance_list_item(obj, instance_map, org_map):
        return {
            "instance_id": obj.id,
            "instance_id_values": list(parse_instance_id(obj.id)),
            "instance_name": obj.name or obj.id,
            "interval": obj.interval,
            "agent_id": instance_map.get(obj.id, {}).get("agent_id", ""),
            "time": instance_map.get(obj.id, {}).get("time", ""),
            "cloud_region_id": obj.cloud_region_id,
            "ip": obj.ip,
            "summary_facts": obj.summary_facts,
            "fallback_sampling_rate": obj.fallback_sampling_rate,
            "node_id": obj.node_id or "",
            "cmdb_id": obj.cmdb_id or "",
            "organizations": list(org_map.get(obj.id, [])),
        }

    @staticmethod
    def _escape_promql_label_value(value):
        value_str = str(value)
        return value_str.replace("\\", "\\\\").replace('"', '\\"')

    @staticmethod
    def generate_monitor_instance_id(monitor_object_id, monitor_instance_name, interval, actor_context=None):
        """生成监控对象实例ID"""
        obj = MonitorInstance.objects.filter(monitor_object_id=monitor_object_id, name=monitor_instance_name).first()
        if obj:
            obj.interval = interval
            for key, value in maintainer_kwargs(actor_context, include_created=False).items():
                setattr(obj, key, value)
            obj.save()
            return obj.id
        else:
            # 生成一个uui
            instance_id = uuid.uuid4().hex
            MonitorInstance.objects.create(
                id=instance_id,
                name=monitor_instance_name,
                interval=interval,
                monitor_object_id=monitor_object_id,
                **maintainer_kwargs(actor_context),
            )

            return instance_id

    @staticmethod
    def check_monitor_instance(monitor_object_id, instance_info):
        """创建监控对象实例"""

        instance_id = str(tuple([instance_info["instance_id"]]))
        objs = MonitorInstance.objects.filter(id=instance_id).first()
        if objs:
            raise BaseAppException(f"实例已存在：{instance_info['instance_name']}")

    @staticmethod
    def autodiscover_monitor_instance():
        """同步监控实例数据"""
        sync_instance_and_group.delay()

    @staticmethod
    def set_object_order(order_data: list):
        """
        设置监控对象排序
        :param order_data: [{"type": "OS", "object_list": ["Host"]}, ...]
        """
        with transaction.atomic():
            type_updates = []
            object_updates = []

            # 仅当传入多个类型时才更新类型排序（单个类型表示只是对象内部重排）
            update_type_order = len(order_data) > 1

            # 批量收集需要更新的数据
            for idx, item in enumerate(order_data):
                type_id = item.get("type")
                object_list = item.get("object_list", [])

                # 创建或获取分类对象
                obj_type, created = MonitorObjectType.objects.get_or_create(id=type_id, defaults={"order": idx})
                if update_type_order and not created and obj_type.order != idx:
                    obj_type.order = idx
                    type_updates.append(obj_type)

                # 收集需要更新的监控对象
                for name_idx, name in enumerate(object_list):
                    objects = MonitorObject.objects.filter(name=name, type_id=type_id)
                    for obj in objects:
                        if obj.order != name_idx:
                            obj.order = name_idx
                            object_updates.append(obj)

            # 批量更新
            if type_updates:
                MonitorObjectType.objects.bulk_update(
                    type_updates,
                    ["order"],
                    batch_size=DatabaseConstants.MONITOR_OBJECT_BATCH_SIZE,
                )
            if object_updates:
                MonitorObject.objects.bulk_update(
                    object_updates,
                    ["order"],
                    batch_size=DatabaseConstants.MONITOR_OBJECT_BATCH_SIZE,
                )

    @staticmethod
    def descendant_object_ids(root_id):
        """按 parent 关系收集全部后代对象 ID，避免环导致死循环。"""
        descendant_ids = []
        frontier = [root_id]
        seen = {root_id}
        while frontier:
            children = list(MonitorObject.objects.filter(parent_id__in=frontier).exclude(id__in=seen).values_list("id", flat=True))
            descendant_ids.extend(children)
            seen.update(children)
            frontier = children
        return descendant_ids

    @staticmethod
    def set_object_visibility(obj: MonitorObject, is_visible: bool) -> None:
        """切换对象可见性，并同步全部子对象，避免父对象隐藏后子对象仍出现在视图中。"""
        target_ids = [obj.id, *MonitorObjectService.descendant_object_ids(obj.id)]
        with transaction.atomic():
            MonitorObject.objects.filter(id__in=target_ids).update(is_visible=is_visible)

    @staticmethod
    def update_instance(instance_id, name=None, organizations=None, actor_context=None, **extra_fields):
        """更新监控对象实例"""
        instance = MonitorInstance.objects.filter(id=instance_id).first()
        if not instance:
            raise BaseAppException("Monitor instance does not exist")
        if name:
            MonitorObjectService.validate_update_instance_name_unique(instance, name)
            instance.name = name
        for field in ("cloud_region_id", "ip", "fallback_sampling_rate", "auto"):
            if field in extra_fields and extra_fields[field] is not None:
                setattr(instance, field, extra_fields[field])
        for key, value in maintainer_kwargs(actor_context, include_created=False).items():
            setattr(instance, key, value)
        instance.save()

        # 更新组织信息
        if organizations is not None:
            instance.monitorinstanceorganization_set.all().delete()
            for org in organizations:
                instance.monitorinstanceorganization_set.create(organization=org)

    @staticmethod
    def remove_instances_organizations(instance_ids, organizations):
        """删除监控对象实例组织"""
        if not instance_ids or not organizations:
            return

        MonitorInstanceOrganization.objects.filter(monitor_instance_id__in=instance_ids, organization__in=organizations).delete()

    @staticmethod
    def add_instances_organizations(instance_ids, organizations):
        """添加监控对象实例组织"""
        if not instance_ids or not organizations:
            return

        creates = []
        for instance_id in instance_ids:
            for org in organizations:
                creates.append(MonitorInstanceOrganization(monitor_instance_id=instance_id, organization=org))
        MonitorInstanceOrganization.objects.bulk_create(creates, ignore_conflicts=True)

    @staticmethod
    def set_instances_organizations(instance_ids, organizations):
        """设置监控对象实例组织"""
        if not instance_ids:
            return
        organizations = organizations or []

        with transaction.atomic():
            # 删除旧的组织关联
            MonitorInstanceOrganization.objects.filter(monitor_instance_id__in=instance_ids).delete()

            # 添加新的组织关联
            creates = []
            for instance_id in instance_ids:
                for org in organizations:
                    creates.append(MonitorInstanceOrganization(monitor_instance_id=instance_id, organization=org))
            if creates:
                MonitorInstanceOrganization.objects.bulk_create(creates, ignore_conflicts=True)
