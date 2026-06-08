"""Playbook序列化器"""

import os

import yaml
from rest_framework import serializers

from apps.core.utils.serializers import TeamSerializer
from apps.job_mgmt.models import Playbook
from apps.job_mgmt.utils.playbook_archive import enforce_archive_limits, open_archive, validate_archive_extension


def parse_playbook_zip(file) -> dict:
    """
    解析 Playbook 压缩包，提取 README、文件列表和参数定义

    支持 .zip, .tar.gz, .tgz 格式

    Returns:
        dict: {
            "readme": str,  # README.md 内容
            "file_list": list,  # 文件路径列表
            "params": list,  # 参数定义 [{"name": ..., "default": ..., "description": ...}]
        }
    """
    result = {"readme": "", "file_list": [], "params": []}

    enforce_archive_limits(file)

    try:
        with open_archive(file) as (archive_type, archive):
            if archive_type == "zip":
                result = _parse_zip(archive)
            else:
                result = _parse_tarball(archive)
    except Exception:
        # 解析失败不影响上传，返回空结果
        pass

    return result


def _build_file_tree(paths: list) -> list:
    """
    将扁平文件路径列表转换为树形结构

    输入: ["nginx-deploy/playbook.yml", "nginx-deploy/roles/nginx/tasks/main.yml"]
    输出: [{"name": "nginx-deploy", "type": "directory", "children": [...]}]
    """
    root = {}

    for path in paths:
        parts = path.strip("/").split("/")
        current = root
        for i, part in enumerate(parts):
            if not part:
                continue
            if part not in current:
                is_file = (i == len(parts) - 1) and not path.endswith("/")
                current[part] = {
                    "name": part,
                    "type": "file" if is_file else "directory",
                    "children": {} if not is_file else None,
                }
            current = current[part].get("children", {}) if current[part]["children"] is not None else {}

    def convert_to_list(node: dict) -> list:
        result = []
        for key in sorted(node.keys()):
            item = node[key]
            entry = {"name": item["name"], "type": item["type"]}
            if item["type"] == "directory" and item["children"]:
                entry["children"] = convert_to_list(item["children"])
            elif item["type"] == "directory":
                entry["children"] = []
            result.append(entry)
        return result

    return convert_to_list(root)


def _parse_zip(archive) -> dict:
    """解析 ZIP 文件"""
    result = {"readme": "", "file_list": [], "params": []}
    paths = []

    paths = archive.namelist()

    for name in archive.namelist():
        lower_name = name.lower()
        # 提取 README
        if lower_name.endswith("readme.md") or lower_name.endswith("readme.txt"):
            result["readme"] = archive.read(name).decode("utf-8", errors="ignore")
        # 提取参数（从 defaults/main.yml 或 vars/main.yml）
        elif lower_name.endswith(("defaults/main.yml", "defaults/main.yaml", "vars/main.yml", "vars/main.yaml")):
            params = _extract_params_from_yaml(archive.read(name))
            if params:
                result["params"].extend(params)

    result["file_list"] = _build_file_tree(paths)
    return result


def _parse_tarball(archive) -> dict:
    """解析 tar.gz/tgz 文件"""
    result = {"readme": "", "file_list": [], "params": []}
    paths = []

    for member in archive.getmembers():
        if member.isdir():
            paths.append(member.name + "/")
        else:
            paths.append(member.name)

    for member in archive.getmembers():
        if not member.isfile():
            continue
        lower_name = member.name.lower()
        # 提取 README
        if lower_name.endswith("readme.md") or lower_name.endswith("readme.txt"):
            f = archive.extractfile(member)
            if f:
                result["readme"] = f.read().decode("utf-8", errors="ignore")
        # 提取参数
        elif lower_name.endswith(("defaults/main.yml", "defaults/main.yaml", "vars/main.yml", "vars/main.yaml")):
            f = archive.extractfile(member)
            if f:
                params = _extract_params_from_yaml(f.read())
                if params:
                    result["params"].extend(params)

    result["file_list"] = _build_file_tree(paths)
    return result


def _extract_params_from_yaml(content: bytes) -> list:
    """
    从 YAML 内容提取参数定义

    返回格式: [{"name": str, "default": any, "description": str}]
    """
    params = []
    try:
        data = yaml.safe_load(content.decode("utf-8", errors="ignore"))
        if not isinstance(data, dict):
            return params

        for key, value in data.items():
            param = {
                "name": key,
                "default": value if not isinstance(value, (dict, list)) else None,
                "description": "",
            }
            params.append(param)
    except Exception:
        pass

    return params


# ============ 文件预览相关函数 ============

# 文件大小限制：1MB
MAX_PREVIEW_SIZE = 1 * 1024 * 1024

# 文件类型映射（扩展名 -> 语言类型）
FILE_TYPE_MAP = {
    ".yml": "yaml",
    ".yaml": "yaml",
    ".md": "markdown",
    ".py": "python",
    ".sh": "bash",
    ".json": "json",
    ".j2": "jinja2",
    ".jinja2": "jinja2",
    ".txt": "text",
    ".cfg": "ini",
    ".ini": "ini",
    ".conf": "ini",
}

# 二进制文件扩展名
BINARY_EXTENSIONS = {".pyc", ".pyo", ".so", ".dll", ".exe", ".bin", ".tar", ".gz", ".zip", ".png", ".jpg", ".jpeg", ".gif", ".ico"}


def get_file_type(file_path: str) -> str:
    """
    根据文件扩展名返回语言类型

    Args:
        file_path: 文件路径

    Returns:
        语言类型字符串，用于前端语法高亮
    """
    ext = os.path.splitext(file_path)[1].lower()
    return FILE_TYPE_MAP.get(ext, "text")


def is_binary_file(file_path: str, content: bytes) -> bool:
    """
    检测文件是否为二进制文件

    判定规则:
    1. 文件扩展名在二进制扩展名列表中
    2. 文件内容前 8KB 包含 null 字节

    Args:
        file_path: 文件路径
        content: 文件内容

    Returns:
        True 如果是二进制文件，否则 False
    """
    # 检查扩展名
    ext = os.path.splitext(file_path)[1].lower()
    if ext in BINARY_EXTENSIONS:
        return True

    # 检查内容是否包含 null 字节（检查前 8KB）
    check_size = min(len(content), 8192)
    return b"\x00" in content[:check_size]


def validate_file_path(file_path: str, valid_paths: list) -> tuple[bool, str]:
    """
    验证文件路径的安全性

    Args:
        file_path: 用户请求的文件路径
        valid_paths: 压缩包内的有效文件路径列表

    Returns:
        (is_valid, error_message) 元组
    """
    # 禁止路径遍历
    if ".." in file_path:
        return False, "非法文件路径"

    # 禁止绝对路径
    if file_path.startswith("/") or file_path.startswith("\\"):
        return False, "非法文件路径"

    # 必须在压缩包文件列表中
    if file_path not in valid_paths:
        return False, "文件不存在"

    return True, ""


def extract_file_from_archive(file_obj, file_path: str) -> dict:
    """
    从压缩包中提取指定文件的内容

    支持 .zip, .tar.gz, .tgz 格式

    Args:
        file_obj: Django FileField 对象
        file_path: 要提取的文件在压缩包内的相对路径

    Returns:
        dict: {
            "file_name": str,      # 文件名
            "file_path": str,      # 完整路径
            "content": str,        # 文件内容
            "file_type": str,      # 语言类型
            "file_size": int,      # 文件大小（字节）
        }

    Raises:
        ValueError: 文件不存在、路径非法、文件过大、二进制文件等
    """
    enforce_archive_limits(file_obj)

    # 获取压缩包内所有文件路径
    valid_paths = []
    with open_archive(file_obj) as (archive_type, archive):
        if archive_type == "zip":
            valid_paths = [name for name in archive.namelist() if not name.endswith("/")]
        else:
            valid_paths = [member.name for member in archive.getmembers() if member.isfile()]

    is_valid, error_msg = validate_file_path(file_path, valid_paths)
    if not is_valid:
        raise ValueError(error_msg)

    extracted_content = None
    file_size = 0

    with open_archive(file_obj) as (archive_type, archive):
        if archive_type == "zip":
            info = archive.getinfo(file_path)
            file_size = info.file_size

            if file_size > MAX_PREVIEW_SIZE:
                raise ValueError(f"文件过大，不支持预览|{file_size}")

            extracted_content = archive.read(file_path)
        else:
            member = archive.getmember(file_path)
            file_size = member.size

            if file_size > MAX_PREVIEW_SIZE:
                raise ValueError(f"文件过大，不支持预览|{file_size}")

            f = archive.extractfile(member)
            if f:
                extracted_content = f.read()

    if extracted_content is None:
        raise ValueError("文件不存在")

    # 检查是否为二进制文件
    if is_binary_file(file_path, extracted_content):
        raise ValueError("不支持预览二进制文件")

    # 解码内容
    try:
        content_str = extracted_content.decode("utf-8")
    except UnicodeDecodeError:
        # 尝试其他编码
        try:
            content_str = extracted_content.decode("gbk")
        except UnicodeDecodeError:
            content_str = extracted_content.decode("utf-8", errors="ignore")

    return {
        "file_name": os.path.basename(file_path),
        "file_path": file_path,
        "content": content_str,
        "file_type": get_file_type(file_path),
        "file_size": file_size,
    }


class PlaybookListSerializer(TeamSerializer):
    """Playbook列表序列化器（返回精简字段）"""

    class Meta:
        model = Playbook
        fields = [
            "id",
            "name",
            "version",
            "team_name",
            "created_by",
            "updated_by",
            "updated_at",
            "description",
        ]


class PlaybookDetailSerializer(serializers.ModelSerializer):
    """Playbook详情序列化器（包含解析后的内容）"""

    class Meta:
        model = Playbook
        fields = [
            "id",
            "name",
            "description",
            "version",
            "readme",
            "file_list",
            "params",
            "created_by",
            "updated_by",
            "updated_at",
        ]
        read_only_fields = fields


class PlaybookCreateSerializer(serializers.Serializer):
    """
    Playbook创建序列化器

    接收文件上传，自动提取文件名作为 Playbook 名称
    """

    file = serializers.FileField(help_text="Playbook ZIP 文件")
    version = serializers.CharField(max_length=32, default="v1.0.0", required=False, help_text="版本号")
    team = serializers.ListField(child=serializers.IntegerField(), default=list, required=False, help_text="团队ID列表")

    def validate_file(self, value):
        """验证上传的文件"""
        if not value:
            raise serializers.ValidationError("文件不能为空")

        try:
            validate_archive_extension(value.name)
            enforce_archive_limits(value)
        except ValueError as err:
            raise serializers.ValidationError(str(err)) from err

        return value

    def create(self, validated_data):
        """创建 Playbook"""
        file = validated_data["file"]
        version = validated_data.get("version", "v1.0.0")
        team = validated_data.get("team", [])

        # 从文件名提取 Playbook 名称（去掉扩展名）
        filename = file.name
        name = os.path.splitext(filename)[0]
        # 处理 .tar.gz 的情况
        if name.endswith(".tar"):
            name = name[:-4]

        # 解析 ZIP 包内容
        parsed = parse_playbook_zip(file)

        # 获取当前用户信息
        request = self.context.get("request")
        username = getattr(request.user, "username", "") if request else ""
        domain = getattr(request.user, "domain", "domain.com") if request else "domain.com"

        # 创建 Playbook
        playbook = Playbook.objects.create(
            name=name,
            version=version,
            file=file,
            team=team,
            readme=parsed["readme"],
            file_list=parsed["file_list"],
            params=parsed["params"],
            created_by=username,
            updated_by=username,
            domain=domain,
            updated_by_domain=domain,
        )

        return playbook


class PlaybookUpdateSerializer(serializers.ModelSerializer):
    """常规修改序列化器

    只允许修改 name, description, team
    """

    class Meta:
        model = Playbook
        fields = ["name", "description", "team"]


class PlaybookUpgradeSerializer(serializers.Serializer):
    """更新版本序列化器

    上传新文件，可选填写版本号（不填则自动 +0.0.1）
    """

    file = serializers.FileField(help_text="新的 Playbook ZIP 文件")
    version = serializers.CharField(max_length=32, required=False, allow_blank=True, help_text="新版本号（不填则自动 +0.0.1）")

    def validate_file(self, value):
        """验证上传的文件"""
        if not value:
            raise serializers.ValidationError("文件不能为空")

        try:
            validate_archive_extension(value.name)
            enforce_archive_limits(value)
        except ValueError as err:
            raise serializers.ValidationError(str(err)) from err

        return value

    def _increment_version(self, current_version: str) -> str:
        """
        版本号自动 +0.0.1

        示例: v1.0.0 -> v1.0.1, 1.2.3 -> 1.2.4
        """
        # 去掉 v 前缀
        version = current_version.lstrip("vV")
        parts = version.split(".")

        try:
            if len(parts) >= 3:
                parts[-1] = str(int(parts[-1]) + 1)
            elif len(parts) == 2:
                parts.append("1")
            else:
                parts = ["1", "0", "1"]
        except ValueError:
            # 版本号格式异常，默认返回
            return "v1.0.1"

        # 保持原始的 v 前缀风格
        prefix = "v" if current_version.startswith(("v", "V")) else ""
        return f"{prefix}{'.'.join(parts)}"

    def update(self, instance, validated_data):
        """
        更新版本

        1. 删除旧文件
        2. 上传新文件
        3. 解析 ZIP 包内容
        4. 更新版本号（自动或手动）
        5. 从文件名更新 name
        """
        file = validated_data["file"]
        new_version = validated_data.get("version", "").strip()

        # 删除旧文件，避免存储泄漏
        if instance.file:
            instance.file.delete(save=False)

        # 版本号逻辑：不填则自动 +0.0.1
        if not new_version:
            new_version = self._increment_version(instance.version)

        # 从文件名提取新的 Playbook 名称
        filename = file.name
        name = os.path.splitext(filename)[0]
        if name.endswith(".tar"):
            name = name[:-4]

        # 解析 ZIP 包内容
        parsed = parse_playbook_zip(file)

        # 获取当前用户信息
        request = self.context.get("request")
        username = getattr(request.user, "username", "") if request else ""
        domain = getattr(request.user, "domain", "domain.com") if request else "domain.com"

        # 更新实例
        instance.file = file
        instance.name = name
        instance.version = new_version
        instance.readme = parsed["readme"]
        instance.file_list = parsed["file_list"]
        instance.params = parsed["params"]
        instance.updated_by = username
        instance.updated_by_domain = domain
        instance.save()

        return instance


class PlaybookBatchDeleteSerializer(serializers.Serializer):
    """Playbook批量删除序列化器"""

    ids = serializers.ListField(child=serializers.IntegerField(), min_length=1, help_text="要删除的PlaybookID列表")
