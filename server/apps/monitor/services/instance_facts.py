import ipaddress
from urllib.parse import urlsplit

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.node_mgmt.constants.controller import ControllerConstants


class InstanceFactResolver:
    """把插件接入输入解析为受约束的非敏感实例事实。"""

    SUPPORTED_RESOLVERS = {"input", "selected_node", "selected_nodes", "compose_endpoint", "constant"}
    SUPPORTED_VALUE_TYPES = {"text", "ip", "endpoint", "node_ref", "node_ref_list"}
    SENSITIVE_FIELD_PARTS = ("password", "token", "secret", "private_key", "credential")
    MAX_TEXT_LENGTH = 1000

    @classmethod
    def validate_bindings(cls, bindings):
        if bindings in (None, ""):
            return []
        if not isinstance(bindings, list):
            raise BaseAppException("instance_fact_bindings 必须是列表")

        normalized = []
        seen_single_facts = set()
        for index, raw_binding in enumerate(bindings):
            if not isinstance(raw_binding, dict):
                raise BaseAppException(f"instance_fact_bindings[{index}] 必须是对象")
            fact = str(raw_binding.get("fact") or "").strip()
            value_type = str(raw_binding.get("value_type") or "").strip()
            resolver = str(raw_binding.get("resolver") or "").strip()
            options = raw_binding.get("options") or {}
            if not fact or not all(part.replace("_", "").replace("-", "").isalnum() for part in fact.split(".")):
                raise BaseAppException(f"instance_fact_bindings[{index}].fact 不合法")
            if value_type not in cls.SUPPORTED_VALUE_TYPES:
                raise BaseAppException(f"实例事实 {fact} 使用了不支持的 value_type: {value_type}")
            if resolver not in cls.SUPPORTED_RESOLVERS:
                raise BaseAppException(f"实例事实 {fact} 使用了不支持的 resolver: {resolver}")
            if not isinstance(options, dict):
                raise BaseAppException(f"实例事实 {fact} 的 options 必须是对象")
            if resolver == "input" and not str(options.get("field") or "").strip():
                raise BaseAppException(f"实例事实 {fact} 的 input resolver 缺少 field")
            if resolver == "constant" and options.get("value") in (None, ""):
                raise BaseAppException(f"实例事实 {fact} 的 constant resolver 缺少 value")

            declared_fields = [options.get("field"), options.get("host_field"), options.get("port_field")]
            for field in declared_fields:
                field_name = str(field or "").lower()
                if field_name and any(part in field_name for part in cls.SENSITIVE_FIELD_PARTS):
                    raise BaseAppException(f"实例事实 {fact} 禁止读取敏感字段: {field}")

            if value_type not in {"node_ref_list"} and fact in seen_single_facts:
                raise BaseAppException(f"单值实例事实重复绑定: {fact}")
            if value_type not in {"node_ref_list"}:
                seen_single_facts.add(fact)
            normalized.append({"fact": fact, "value_type": value_type, "resolver": resolver, "options": options})
        return normalized

    @classmethod
    def resolve(cls, plugin, instance_input, trusted_context=None):
        bindings = cls.validate_bindings(getattr(plugin, "instance_fact_bindings", []) or [])
        context = trusted_context or {}
        facts = {}
        for binding in bindings:
            value = cls._resolve_binding(binding, instance_input, context)
            if value not in (None, "", []):
                facts[binding["fact"]] = value
        return facts

    @classmethod
    def merge(cls, existing, generated, source=None):
        merged = dict(existing or {})
        source_map = {fact: dict(contributions) for fact, contributions in (merged.get("_sources") or {}).items() if isinstance(contributions, dict)}
        for fact, value in (generated or {}).items():
            if fact.startswith("_"):
                continue
            previous = merged.get(fact)
            if value in (None, "", []):
                continue
            if source:
                contributions = source_map.setdefault(fact, {})
                if not contributions and previous not in (None, "", []):
                    contributions["legacy"] = previous
                contributions[str(source)] = value
                distinct_values = {repr(item) for item in contributions.values() if item not in (None, "", [])}
                if len(distinct_values) > 1:
                    raise BaseAppException(f"实例事实冲突: {fact}")
                merged[fact] = value
            else:
                if previous not in (None, "", []) and previous != value:
                    raise BaseAppException(f"实例事实冲突: {fact}")
                merged[fact] = value
        if source_map:
            merged["_sources"] = source_map
        return merged

    @classmethod
    def _resolve_binding(cls, binding, instance_input, context):
        resolver = binding["resolver"]
        options = binding["options"]
        skip_required = False
        if resolver == "input":
            raw_value = instance_input.get(options.get("field"))
        elif resolver == "constant":
            raw_value = options.get("value")
        elif resolver == "selected_node":
            nodes = cls._selected_nodes(instance_input, context, options)
            raw_value = nodes[0].get(options.get("node_field", "ip")) if nodes else None
            raw_value, skip_required = cls._map_container_node_ip(
                nodes[0] if nodes else None,
                options.get("node_field", "ip"),
                raw_value,
            )
        elif resolver == "selected_nodes":
            return [cls._node_ref(node) for node in cls._selected_nodes(instance_input, context, options)]
        elif resolver == "compose_endpoint":
            host = str(instance_input.get(options.get("host_field", "host")) or "").strip()
            port = instance_input.get(options.get("port_field", "port"))
            if not host:
                return None
            host_part = f"[{host}]" if ":" in host and not host.startswith("[") else host
            raw_value = f"{host_part}:{port}" if port not in (None, "") else host
        else:  # pragma: no cover - validate_bindings 已拦截
            raise BaseAppException(f"不支持的实例事实解析器: {resolver}")
        normalized = cls._normalize(raw_value, binding["value_type"])
        if skip_required:
            return normalized
        if raw_value in (None, "") and options.get("required") is True:
            raise BaseAppException(f"必需实例事实缺失: {binding['fact']}")
        if raw_value not in (None, "") and normalized in (None, "", []) and options.get("required") is True:
            raise BaseAppException(f"必需实例事实无法规整: {binding['fact']}")
        return normalized

    @classmethod
    def _map_container_node_ip(cls, node, node_field, raw_value):
        """容器节点无可用 node.ip 时回退云区域展示 IP；域名不入库。"""
        if str(node_field or "ip") != "ip" or not cls._is_container_node(node):
            return raw_value, False
        if cls._normalize(raw_value, "ip"):
            return raw_value, False
        mapped = (node or {}).get("region_display_ip")
        if cls._normalize(mapped, "ip"):
            return mapped, False
        return None, True

    @staticmethod
    def _is_container_node(node):
        return bool(node) and str(node.get("node_type") or "") == ControllerConstants.NODE_TYPE_CONTAINER

    @staticmethod
    def _selected_nodes(instance_input, context, options):
        selection_field = options.get("selection_field", "node_ids")
        raw_selection = instance_input.get(selection_field, [])
        if not isinstance(raw_selection, (list, tuple)):
            raw_selection = [raw_selection]
        selected_ids = [str(value) for value in raw_selection if value not in (None, "")]
        node_map = {str(node.get("id")): node for node in context.get("nodes", []) if node.get("id") not in (None, "")}
        missing = [node_id for node_id in selected_ids if node_id not in node_map]
        if missing:
            raise BaseAppException(f"实例事实无法解析节点: {', '.join(missing)}")
        return [node_map[node_id] for node_id in selected_ids]

    @classmethod
    def _normalize(cls, raw_value, value_type):
        value = str(raw_value or "").strip()
        if not value:
            return None
        if len(value) > cls.MAX_TEXT_LENGTH:
            raise BaseAppException("实例事实值超过最大长度")
        if value_type == "ip":
            for candidate in value.split(","):
                candidate = candidate.strip()
                try:
                    return str(ipaddress.ip_address(candidate.strip("[]")))
                except ValueError:
                    try:
                        parsed = urlsplit(candidate if "://" in candidate else f"//{candidate}")
                        return str(ipaddress.ip_address((parsed.hostname or "").strip("[]")))
                    except ValueError:
                        continue
            return None
        return value

    @staticmethod
    def _node_ref(node):
        return {
            "id": str(node.get("id") or ""),
            "name": str(node.get("name") or ""),
            "ip": str(node.get("ip") or ""),
        }
