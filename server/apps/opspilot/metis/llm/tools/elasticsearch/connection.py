from typing import Any, Dict, Optional

from elasticsearch import Elasticsearch
from langchain_core.runnables import RunnableConfig


def build_es_config_from_runnable(config: Optional[RunnableConfig]) -> Dict[str, Any]:
    configurable = config.get("configurable", {}) if config else {}
    url = configurable.get("url") or "http://127.0.0.1:9200"
    result = {
        "hosts": [url],
        "verify_certs": configurable.get("verify_certs", True),
        "request_timeout": configurable.get("request_timeout", 30),
    }

    if configurable.get("api_key"):
        result["api_key"] = configurable.get("api_key")
    elif configurable.get("username") or configurable.get("password"):
        result["http_auth"] = (configurable.get("username", ""), configurable.get("password", ""))

    if configurable.get("ca_certs"):
        result["ca_certs"] = configurable.get("ca_certs")
    if configurable.get("client_cert"):
        result["client_cert"] = configurable.get("client_cert")
    if configurable.get("client_key"):
        result["client_key"] = configurable.get("client_key")

    return result


def get_es_client(config: Optional[RunnableConfig] = None):
    return Elasticsearch(**build_es_config_from_runnable(config))
