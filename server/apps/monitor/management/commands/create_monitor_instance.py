from copy import deepcopy
from pathlib import Path
import uuid

import yaml
from django.apps import apps
from django.core.management import BaseCommand, CommandError

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.monitor.services.node_mgmt import InstanceConfigService
from apps.monitor.utils.dimension import parse_instance_id


class Command(BaseCommand):
    help = "通过 YAML 调用 node_mgmt 创建监控实例"

    def add_arguments(self, parser):
        parser.add_argument("--config", required=True, type=str, help="请求 YAML 文件路径")
        parser.add_argument("--output", required=True, type=str, help="结果 YAML 文件路径")

    def handle(self, *args, **options):
        request_data = self._load_config(options["config"])
        self._validate_request(request_data)

        service_data = deepcopy(request_data)
        self._fill_missing_instance_ids(service_data)
        try:
            InstanceConfigService.create_monitor_instance_by_node_mgmt(service_data)
        except BaseAppException as error:
            raise CommandError(str(error)) from error
        except Exception as error:
            raise CommandError(f"创建监控实例失败: {error}") from error

        result = {
            "request": request_data,
            "result": {
                "status": "success",
                "instances": self._build_instances_output(service_data),
            },
        }
        output_path = self._write_output(options["output"], result)
        self.stdout.write(f"创建监控实例成功，结果文件已生成: {output_path}")

    def _load_config(self, config_path):
        path = Path(config_path)
        if not path.exists() or not path.is_file():
            raise CommandError(f"YAML 配置文件不存在: {config_path}")

        try:
            with path.open("r", encoding="utf-8") as file:
                data = yaml.safe_load(file) or {}
        except yaml.YAMLError as error:
            raise CommandError(f"YAML 配置解析失败: {error}") from error
        except OSError as error:
            raise CommandError(f"YAML 配置读取失败: {error}") from error

        if not isinstance(data, dict):
            raise CommandError("YAML 配置内容必须是对象")
        return data

    def _validate_request(self, data):
        required_fields = ["monitor_object_id", "collector", "collect_type", "configs", "instances"]
        missing_fields = [field for field in required_fields if field not in data or data[field] in [None, ""]]
        if missing_fields:
            raise CommandError(f"缺少必填参数: {', '.join(missing_fields)}")

        if not isinstance(data["configs"], list) or not data["configs"]:
            raise CommandError("configs 必须是非空数组")
        if not isinstance(data["instances"], list) or not data["instances"]:
            raise CommandError("instances 必须是非空数组")

        for index, config in enumerate(data["configs"]):
            if not isinstance(config, dict):
                raise CommandError(f"configs[{index}] 必须是对象")
            if not config.get("type"):
                raise CommandError(f"configs[{index}].type 必填")

        for index, instance in enumerate(data["instances"]):
            if not isinstance(instance, dict):
                raise CommandError(f"instances[{index}] 必须是对象")
            for field in ["instance_name", "group_ids"]:
                if field not in instance or instance[field] in [None, ""]:
                    raise CommandError(f"instances[{index}].{field} 必填")
            if not isinstance(instance["group_ids"], list):
                raise CommandError(f"instances[{index}].group_ids 必须是数组")

    def _fill_missing_instance_ids(self, data):
        for instance in data.get("instances", []):
            if instance.get("instance_id") not in [None, ""]:
                continue
            instance["instance_id"] = self._generate_instance_id(instance)

    def _generate_instance_id(self, instance):
        instance_name = str(instance.get("instance_name", "")).strip()
        if instance_name:
            return f"cmd_{uuid.uuid5(uuid.NAMESPACE_DNS, instance_name).hex}"
        return f"cmd_{uuid.uuid4().hex}"

    def _build_instances_output(self, service_data):
        monitor_instance_model = apps.get_model("monitor", "MonitorInstance")
        monitor_org_model = apps.get_model("monitor", "MonitorInstanceOrganization")
        collect_config_model = apps.get_model("monitor", "CollectConfig")

        requested_instance_ids = [instance["instance_id"] for instance in service_data.get("instances", [])]
        if not requested_instance_ids:
            return []

        instance_map = {
            instance.id: instance
            for instance in monitor_instance_model.objects.select_related("monitor_object").filter(id__in=requested_instance_ids)
        }

        organization_map = {}
        organization_qs = monitor_org_model.objects.filter(monitor_instance_id__in=requested_instance_ids).values_list(
            "monitor_instance_id", "organization"
        )
        for instance_id, organization in organization_qs:
            if instance_id not in organization_map:
                organization_map[instance_id] = []
            organization_map[instance_id].append(organization)

        config_map = {}
        config_qs = collect_config_model.objects.filter(monitor_instance_id__in=requested_instance_ids).values(
            "id",
            "monitor_instance_id",
            "collector",
            "collect_type",
            "config_type",
            "monitor_plugin_id",
            "is_child",
        )
        for config in config_qs:
            instance_id = config.pop("monitor_instance_id")
            if instance_id not in config_map:
                config_map[instance_id] = []
            config_map[instance_id].append(config)

        results = []
        for requested in service_data.get("instances", []):
            instance_id = requested["instance_id"]
            instance = instance_map.get(instance_id)
            if not instance:
                continue
            results.append(
                {
                    "instance_id": instance.id,
                    "instance_id_values": list(parse_instance_id(instance.id)),
                    "instance_name": instance.name,
                    "monitor_object_id": instance.monitor_object_id,
                    "monitor_object_name": instance.monitor_object.name if instance.monitor_object else "",
                    "organizations": organization_map.get(instance.id, []),
                    "interval": instance.interval,
                    "is_active": instance.is_active,
                    "is_deleted": instance.is_deleted,
                    "auto": instance.auto,
                    "configs": config_map.get(instance.id, []),
                    "created_at": instance.created_at.isoformat() if getattr(instance, "created_at", None) else None,
                    "updated_at": instance.updated_at.isoformat() if getattr(instance, "updated_at", None) else None,
                }
            )
        return results

    def _write_output(self, output_path, data):
        path = Path(output_path)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("w", encoding="utf-8") as file:
                yaml.safe_dump(data, file, allow_unicode=True, sort_keys=False)
        except OSError as error:
            raise CommandError(f"结果文件写入失败: {error}") from error
        return path
