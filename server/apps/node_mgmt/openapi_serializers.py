"""node 对外暴露专用 serializer（schema 即契约，字段只增不删不改名）。"""

from rest_framework import serializers

from apps.core.openapi.serializers import OpenAPIRequestSerializer, PaginatedRequestSerializer


class NodePageQuerySerializer(PaginatedRequestSerializer):
    page = serializers.IntegerField(required=False, default=1, min_value=1)
    page_size = serializers.IntegerField(required=False, default=20, min_value=1)
    keyword = serializers.CharField(required=False, default="", allow_blank=True, max_length=128)


class NodeCloudRegionQuerySerializer(NodePageQuerySerializer):
    """云区域目录。组织身份只允许由网关注入。"""


class NodeListQuerySerializer(NodePageQuerySerializer):
    """节点列表。组织身份只允许由网关注入。"""

    cloud_region_id = serializers.IntegerField(required=False, min_value=1)


class NodeDetailQuerySerializer(OpenAPIRequestSerializer):
    """单个节点。组织身份只允许由网关注入。"""

    node_id = serializers.CharField(max_length=100)


class NodePackageQuerySerializer(NodePageQuerySerializer):
    """安装控制器或采集器时选择安装包。只能查询。"""

    package_type = serializers.ChoiceField(choices=("controller", "collector"), required=False)
    os = serializers.CharField(required=False, allow_blank=True, max_length=20)


class NodeInstallTargetSerializer(OpenAPIRequestSerializer):
    """远程安装控制器的一台目标主机。组织由令牌决定，不接受调用方指定。"""

    ip = serializers.CharField(max_length=100)
    node_name = serializers.CharField(required=False, allow_blank=True, default="", max_length=200)
    os = serializers.CharField(required=False, allow_blank=True, max_length=20)
    cpu_architecture = serializers.CharField(required=False, allow_blank=True, max_length=20)
    port = serializers.IntegerField(required=False, min_value=1, max_value=65535)
    username = serializers.CharField(required=False, allow_blank=True, default="", max_length=100)
    password = serializers.CharField(required=False, allow_blank=True, default="", max_length=4096)
    private_key = serializers.CharField(required=False, allow_blank=True, default="", max_length=20000)
    passphrase = serializers.CharField(required=False, allow_blank=True, default="", max_length=4096)
    node_id = serializers.CharField(required=False, allow_blank=True, max_length=100)
    winrm_scheme = serializers.ChoiceField(choices=("http", "https"), required=False, default="https")
    winrm_transport = serializers.ChoiceField(choices=("basic", "ntlm", "kerberos", "credssp"), required=False, default="ntlm")
    winrm_cert_validation = serializers.BooleanField(required=False, default=False)


class NodeControllerInstallSerializer(OpenAPIRequestSerializer):
    """节点页远程安装控制器，返回任务号。"""

    cloud_region_id = serializers.IntegerField(min_value=1)
    work_node = serializers.CharField(max_length=100)
    package_id = serializers.IntegerField(min_value=1)
    cpu_architecture = serializers.CharField(max_length=20)
    nodes = NodeInstallTargetSerializer(many=True, allow_empty=False)


class NodeInstallCommandSerializer(OpenAPIRequestSerializer):
    """节点页手动安装，返回在目标主机执行的命令。"""

    ip = serializers.CharField(max_length=100)
    node_id = serializers.CharField(max_length=100)
    os = serializers.CharField(max_length=20)
    cpu_architecture = serializers.CharField(max_length=20)
    package_id = serializers.IntegerField(min_value=1)
    cloud_region_id = serializers.IntegerField(min_value=1)
    node_name = serializers.CharField(required=False, allow_blank=True, default="", max_length=200)


class NodeInstallTaskQuerySerializer(OpenAPIRequestSerializer):
    """查看控制器或采集器安装进度。"""

    task_type = serializers.ChoiceField(choices=("controller", "collector"))
    task_id = serializers.IntegerField(min_value=1)


class NodeCollectorInstallSerializer(OpenAPIRequestSerializer):
    """在已有节点上安装采集器，返回任务号。"""

    package_id = serializers.IntegerField(min_value=1)
    node_ids = serializers.ListField(child=serializers.CharField(max_length=100), allow_empty=False)


class NodeCollectorOperateSerializer(OpenAPIRequestSerializer):
    """启停本组织节点上的采集器。"""

    node_ids = serializers.ListField(child=serializers.CharField(max_length=100), allow_empty=False)
    collector_id = serializers.CharField(max_length=100)
    operation = serializers.ChoiceField(choices=("start", "restart", "stop"))


class NodeConfigurationBindSerializer(OpenAPIRequestSerializer):
    """把一条采集配置绑定到本组织节点并下发。"""

    node_ids = serializers.ListField(child=serializers.CharField(max_length=100), allow_empty=False)
    collector_configuration_id = serializers.CharField(max_length=100)
