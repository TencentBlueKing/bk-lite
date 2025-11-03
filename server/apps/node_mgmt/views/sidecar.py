from rest_framework.decorators import action

from apps.core.utils.open_base import OpenAPIViewSet
from apps.node_mgmt.services.sidecar import Sidecar
from apps.node_mgmt.utils.token_auth import check_token_auth


class OpenSidecarViewSet(OpenAPIViewSet):
    """
    Sidecar 客户端 API 视图集

    提供节点管理系统中 Sidecar 客户端所需的核心接口，包括：
    - 版本信息获取
    - 采集器列表查询
    - 配置信息获取与渲染
    - 节点信息更新

    所有接口均支持通过 X-Encryption-Key 请求头进行响应加密
    """

    @action(detail=False, methods=["get"], url_path="node")
    def server_info(self, request):
        """
        获取服务端版本信息

        API: GET /node

        Query Parameters:
            node_id (str, required): 节点唯一标识符，用于身份验证

        Request Headers:
            Authorization (str, required): Bearer token 认证
            X-Encryption-Key (str, optional): 用于响应加密的密钥

        Response (200 OK):
            {
                "version": "5.0.0"  # 服务端版本号
            }

        Response Headers:
            Content-Type: application/json

        Authentication:
            需要通过 token 验证节点身份

        示例:
            GET /node?node_id=node-123
        """
        node_id = request.query_params.get("node_id")
        check_token_auth(node_id, request)
        return Sidecar.get_version(request)

    @action(detail=False, methods=["get"], url_path="node/sidecar/collectors")
    def collectors(self, request):
        """
        获取可用的采集器列表

        API: GET /node/sidecar/collectors

        Query Parameters:
            node_id (str, required): 节点唯一标识符，用于身份验证

        Request Headers:
            Authorization (str, required): Bearer token 认证
            If-None-Match (str, optional): ETag 值，用于缓存验证
            X-Encryption-Key (str, optional): 用于响应加密的密钥

        Response (200 OK):
            {
                "collectors": [
                    {
                        "id": "collector-1",
                        "name": "Metrics Collector",
                        "type": "metrics",
                        "enabled": true,
                        "node_operating_system": "linux",
                        ...  # 其他采集器字段（不包含 default_template）
                    },
                    ...
                ]
            }

        Response (304 Not Modified):
            当客户端提供的 ETag 与当前资源匹配时返回，表示采集器列表未变更

        Response Headers:
            ETag: "abc123..."  # 资源版本标识
            Content-Type: application/json

        Authentication:
            需要通过 token 验证节点身份

        Caching:
            支持 ETag 缓存机制，客户端可通过 If-None-Match 避免重复传输

        示例:
            GET /node/sidecar/collectors?node_id=node-123
            If-None-Match: "abc123..."
        """
        node_id = request.query_params.get("node_id")
        check_token_auth(node_id, request)
        return Sidecar.get_collectors(request)

    @action(detail=False, methods=["get"],
            url_path="node/sidecar/configurations/render/(?P<node_id>.+?)/(?P<configuration_id>.+?)")
    def configuration(self, request, node_id, configuration_id):
        """
        获取渲染后的采集器配置

        API: GET /node/sidecar/configurations/render/{node_id}/{configuration_id}

        Path Parameters:
            node_id (str, required): 节点唯一标识符
            configuration_id (str, required): 配置唯一标识符

        Request Headers:
            Authorization (str, required): Bearer token 认证
            If-None-Match (str, optional): ETag 值，用于缓存验证
            X-Encryption-Key (str, optional): 用于响应加密的密钥

        Response (200 OK):
            {
                "id": "config-123",                    # 配置ID
                "collector_id": "collector-456",       # 关联的采集器ID
                "name": "Metrics Collection Config",   # 配置名称
                "template": "...rendered template...", # 渲染后的配置模板内容（已合并子配置并替换变量）
                "env_config": {                        # 环境变量配置（不含敏感信息如密码）
                    "key1": "value1",
                    ...
                }
            }

        Response (304 Not Modified):
            当客户端提供的 ETag 与当前配置匹配时返回

        Response (404 Not Found):
            {
                "error": "Node not found"  # 或 "Configuration not found"
            }

        Response Headers:
            ETag: "def456..."  # 配置版本标识
            Content-Type: application/json

        Authentication:
            需要通过 token 验证节点身份

        Template Rendering:
            - 合并主配置和所有子配置的模板内容
            - 使用节点信息和环境变量渲染模板中的 ${变量}
            - NATS_PASSWORD 等敏感信息不在此处渲染，需通过 env_config 接口获取

        Caching:
            支持 ETag 缓存机制

        示例:
            GET /node/sidecar/configurations/render/node-123/config-456
            If-None-Match: "def456..."
        """
        check_token_auth(node_id, request)
        return Sidecar.get_node_config(request, node_id, configuration_id)

    @action(detail=False, methods=["get"],
            url_path="node/sidecar/env_config/(?P<node_id>.+?)/(?P<configuration_id>.+?)")
    def configuration_env(self, request, node_id, configuration_id):
        """
        获取采集器配置的加密环境变量

        API: GET /node/sidecar/env_config/{node_id}/{configuration_id}

        Path Parameters:
            node_id (str, required): 节点唯一标识符
            configuration_id (str, required): 配置唯一标识符

        Request Headers:
            Authorization (str, required): Bearer token 认证
            X-Encryption-Key (str, required): 用于响应加密的密钥（强烈建议）

        Response (200 OK):
            {
                "id": "config-123",           # 配置ID
                "env_config": {               # 环境变量配置（包含敏感信息）
                    "NATS_PASSWORD": "secret123",  # 来自云区域的 NATS 密码（已解密）
                    "DB_PASSWORD": "dbpass456",    # 配置级密码（已解密）
                    "API_KEY": "key789",           # 其他环境变量
                    ...
                }
            }

        Response (404 Not Found):
            {
                "error": "Node not found"  # 或 "Configuration not found"
            }

        Response Headers:
            Content-Type: application/json

        Authentication:
            需要通过 token 验证节点身份

        Security:
            - 响应包含敏感信息（密码、密钥等），应使用 X-Encryption-Key 加密传输
            - 客户端收到加密响应后，使用 X-Encryption-Key 解密
            - 环境变量按优先级合并：云区域环境变量 < 主配置 env_config < 子配置 env_config
            - 所有包含 'password' 的字段都会自动从数据库密文解密

        示例:
            GET /node/sidecar/env_config/node-123/config-456
            X-Encryption-Key: "encryption-key-base64"
        """
        check_token_auth(node_id, request)
        return Sidecar.get_node_config_env(request, node_id, configuration_id)

    @action(detail=False, methods=["PUT"], url_path="node/sidecars/(?P<node_id>.+?)")
    def update_sidecar_client(self, request, node_id):
        """
        更新 Sidecar 客户端节点信息

        API: PUT /node/sidecars/{node_id}

        Path Parameters:
            node_id (str, required): 节点唯一标识符

        Request Headers:
            Authorization (str, required): Bearer token 认证
            If-None-Match (str, optional): ETag 值，用于缓存验证
            X-Encryption-Key (str, optional): 用于响应加密的密钥
            Content-Type: application/json

        Request Body:
            {
                "node_name": "node-prod-01",  # 节点名称
                "node_details": {             # 节点详细信息
                    "ip": "192.168.1.100",
                    "operating_system": "Linux",  # 操作系统（会转为小写）
                    "architecture": "x86_64",
                    "kernel_version": "5.10.0",
                    "collector_configuration_directory": "/etc/collectors",
                    "status": {               # 节点状态信息
                        "cpu_usage": 45.2,
                        "memory_usage": 60.5,
                        ...
                    },
                    "tags": [                 # 标签（用于分组和云区域关联）
                        {"key": "group", "value": "production"},
                        {"key": "cloud", "value": "1"},  # 云区域ID
                        ...
                    ]
                }
            }

        Response (202 Accepted):
            {
                "configuration": {
                    "update_interval": 5,     # 配置更新间隔（秒）
                    "send_status": true       # 是否发送状态信息
                },
                "configuration_override": true,  # 是否覆盖本地配置
                "actions": [                     # 采集器操作指令（如有待执行操作）
                    {
                        "action": "restart",
                        "collector_id": "collector-123",
                        ...
                    }
                ],
                "assignments": [                 # 分配给该节点的配置列表
                    {
                        "collector_id": "collector-123",
                        "configuration_id": "config-456"
                    },
                    ...
                ]
            }

        Response (304 Not Modified):
            当客户端提供的 ETag 与当前节点配置匹配时返回，仅更新节点状态和时间戳

        Response Headers:
            ETag: "xyz789..."  # 新的节点配置版本标识
            Content-Type: application/json

        Authentication:
            需要通过 token 验证节点身份

        Business Logic:
            - 首次调用：创建节点、关联组织、创建默认配置
            - 后续调用：更新节点信息、更新组织关联（覆盖模式）
            - 处理待执行操作（actions）并在响应后删除
            - 返回分配给该节点的所有配置信息

        Caching:
            - 支持 ETag 缓存机制
            - 即使返回 304，也会更新节点的 updated_at 和 status

        示例:
            PUT /node/sidecars/node-123
            If-None-Match: "xyz789..."

            {
                "node_name": "prod-web-01",
                "node_details": {
                    "ip": "10.0.1.50",
                    "operating_system": "linux",
                    "status": {"cpu": 30},
                    "tags": [{"key": "group", "value": "web"}]
                }
            }
        """
        check_token_auth(node_id, request)
        return Sidecar.update_node_client(request, node_id)
