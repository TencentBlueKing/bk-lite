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

    @staticmethod
    def json_to_toml(json_config):
        key1, key2 = json_config["plugin"]
        if json_config.get("_toml_document"):
            data = deepcopy(json_config["_toml_document"])
            data.setdefault(key1, {}).setdefault(key2, [{}])
            data[key1][key2][0] = json_config["config"]
        else:
            data = {key1: {key2: [json_config["config"]]}}
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
