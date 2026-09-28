import toml
import yaml
from copy import deepcopy
from urllib.parse import urlencode, urlparse, parse_qs

class ConfigFormat:
    @staticmethod
    def toml_to_dict(toml_config):
        config_dict = toml.loads(toml_config)
        plugin = None

        # Telegraf 子配置可能同时包含 inputs、processors 等多个顶层段。
        # 编辑表单对应的是采集输入，不能把遍历到的最后一个 processor 当成配置。
        namespaces = [
            ("inputs", config_dict.get("inputs", {})),
            *[(key, value) for key, value in config_dict.items() if key != "inputs"],
        ]
        for key1, value1 in namespaces:
            if not isinstance(value1, dict):
                continue
            for key2, value2 in value1.items():
                if isinstance(value2, list) and value2:
                    plugin = (key1, key2)
                    break
            if plugin:
                break

        if not plugin:
            return {}

        key1, key2 = plugin
        return {
            "plugin": plugin,
            "config": config_dict[key1][key2][0],
            # 更新时用于保留同一 TOML 中不属于编辑表单的 processors 等配置。
            "_toml_document": config_dict,
        }

    # Telegraf inputs.prometheus.http_headers 的值类型是 map[string]string。
    # 编辑页 switch/inputNumber 会把 bool/number 写进 JSON，再经 json_to_toml 落成
    # verify_tls = false / timeout = 60，Telegraf 直接拒绝加载。
    # 编辑保存前把任意 http_headers 表内的值统一成字符串（bool 用小写 true/false）。
    _QUEUE_NAME_LIST_KEYS = frozenset({"queue_name_include", "queue_name_exclude"})

    @staticmethod
    def _stringify_http_header_value(value):
        """http_headers 值必须是字符串；bool 用小写，避免 Python str(True)=='True'。"""
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, (int, float)):
            # bool 已在上面处理；整数不带小数点，与创建态 Jinja 渲染一致。
            if isinstance(value, float) and value.is_integer():
                return str(int(value))
            return str(value)
        if isinstance(value, list):
            # 兼容 metrics_modules 等被 to_form.array 拆成列表后回写的情况。
            parts = []
            for item in value:
                if item is None or item == "":
                    continue
                parts.append(ConfigFormat._stringify_http_header_value(item) if not isinstance(item, str) else item)
            return ",".join(parts)
        if value is None:
            return ""
        return value if isinstance(value, str) else str(value)

    @staticmethod
    def _coerce_http_headers_to_strings(node):
        if isinstance(node, dict):
            headers = node.get("http_headers")
            if isinstance(headers, dict):
                node["http_headers"] = {
                    key: ConfigFormat._stringify_http_header_value(val)
                    for key, val in headers.items()
                }
            for val in node.values():
                ConfigFormat._coerce_http_headers_to_strings(val)
        elif isinstance(node, list):
            for item in node:
                ConfigFormat._coerce_http_headers_to_strings(item)

    @staticmethod
    def _coerce_queue_name_lists(node):
        """RabbitMQ queue_name_* 创建态经 to_toml_str_array 写成 []string；
        编辑页是 input，会把逗号串直接写回。保存前拆成字符串数组。"""
        if isinstance(node, dict):
            for key, val in list(node.items()):
                if key in ConfigFormat._QUEUE_NAME_LIST_KEYS:
                    if isinstance(val, str):
                        node[key] = [part.strip() for part in val.split(",") if part.strip()]
                    elif isinstance(val, list):
                        node[key] = [
                            str(item).strip()
                            for item in val
                            if item is not None and str(item).strip() != ""
                        ]
                else:
                    ConfigFormat._coerce_queue_name_lists(val)
        elif isinstance(node, list):
            for item in node:
                ConfigFormat._coerce_queue_name_lists(item)

    @staticmethod
    def _normalize_telegraf_types_before_dump(data):
        ConfigFormat._coerce_http_headers_to_strings(data)
        ConfigFormat._coerce_queue_name_lists(data)

    @staticmethod
    def json_to_toml(json_config):
        key1, key2 = json_config["plugin"]
        if json_config.get("_toml_document"):
            data = deepcopy(json_config["_toml_document"])
            data.setdefault(key1, {}).setdefault(key2, [{}])
            # deepcopy config，避免规范化时改到调用方仍持有的表单对象。
            data[key1][key2][0] = deepcopy(json_config["config"])
        else:
            data = {key1: {key2: [deepcopy(json_config["config"])]}}
        ConfigFormat._normalize_telegraf_types_before_dump(data)
        result = toml.dumps(data)
        # toml.dumps 会为数组表补一个空的顶层父表；Telegraf 配置只需要
        # [[inputs.snmp]] / [[processors.enum]] 这样的实际插件段。
        for namespace in data:
            result = result.replace(f"[{namespace}]\n", "")
        return result

    @staticmethod
    def yaml_to_dict(yaml_config):
        """将 YAML 格式的配置转换为字典"""
        return yaml.safe_load(yaml_config)

    @staticmethod
    def json_to_yaml(json_config):
        """将 JSON 格式的配置转换为 YAML 格式"""
        return yaml.dump(json_config, default_flow_style=False)

    @staticmethod
    def query_params_to_url(base_url, query_params):
        """将 JSON 格式的 query_params 转换回原始 URL 格式"""
        query_string = urlencode(query_params, doseq=True)  # 生成查询字符串
        return f"{base_url}?{query_string}"

    @staticmethod
    def extract_query_params(url):
        """解析 URL 并提取查询参数"""
        parsed_url = urlparse(url)  # 解析 URL
        query_params = parse_qs(parsed_url.query)  # 解析查询参数
        # 转换 query_params，去掉列表包装
        query_params = {k: v[0] if len(v) == 1 else v for k, v in query_params.items()}
        return query_params
