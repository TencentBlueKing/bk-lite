from typing import Any, Dict, Optional
from urllib.parse import urlparse

import redis
from langchain_core.runnables import RunnableConfig
from redis.cluster import RedisCluster


def parse_redis_url(url: str) -> Dict[str, Any]:
    parsed = urlparse(url)
    db = 0
    if parsed.path and parsed.path != "/":
        try:
            db = int(parsed.path.strip("/"))
        except ValueError:
            db = 0
    return {
        "host": parsed.hostname or "127.0.0.1",
        "port": parsed.port or 6379,
        "db": db,
        "username": parsed.username,
        "password": parsed.password,
        "ssl": parsed.scheme == "rediss",
    }


def build_redis_config_from_runnable(config: Optional[RunnableConfig]) -> Dict[str, Any]:
    configurable = config.get("configurable", {}) if config else {}
    redis_url = configurable.get("url") or configurable.get("redis_url")
    if redis_url:
        parsed = parse_redis_url(redis_url)
        if configurable.get("username"):
            parsed["username"] = configurable.get("username")
        if configurable.get("password"):
            parsed["password"] = configurable.get("password")
        if configurable.get("ssl") is not None:
            parsed["ssl"] = configurable.get("ssl")
        parsed["ssl_ca_path"] = configurable.get("ssl_ca_path")
        parsed["ssl_keyfile"] = configurable.get("ssl_keyfile")
        parsed["ssl_certfile"] = configurable.get("ssl_certfile")
        parsed["ssl_cert_reqs"] = configurable.get("ssl_cert_reqs")
        parsed["ssl_ca_certs"] = configurable.get("ssl_ca_certs")
        parsed["cluster_mode"] = configurable.get("cluster_mode", False)
        return parsed
    return {
        "host": configurable.get("host", "127.0.0.1"),
        "port": configurable.get("port", 6379),
        "db": configurable.get("db", 0),
        "username": configurable.get("username"),
        "password": configurable.get("password"),
        "ssl": configurable.get("ssl", False),
        "ssl_ca_path": configurable.get("ssl_ca_path"),
        "ssl_keyfile": configurable.get("ssl_keyfile"),
        "ssl_certfile": configurable.get("ssl_certfile"),
        "ssl_cert_reqs": configurable.get("ssl_cert_reqs"),
        "ssl_ca_certs": configurable.get("ssl_ca_certs"),
        "cluster_mode": configurable.get("cluster_mode", False),
    }


def get_redis_connection(config: Optional[RunnableConfig] = None, decode_responses: bool = True):
    params = build_redis_config_from_runnable(config)
    cluster_mode = params.pop("cluster_mode", False)
    params["decode_responses"] = decode_responses
    if cluster_mode:
        params.pop("db", None)
        return RedisCluster(**{k: v for k, v in params.items() if v is not None})
    return redis.Redis(**{k: v for k, v in params.items() if v is not None})


def get_binary_redis_connection(config: Optional[RunnableConfig] = None):
    return get_redis_connection(config=config, decode_responses=False)
