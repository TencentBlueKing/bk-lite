"""Playbook序列化器"""

import io
import os
import tarfile
import zipfile

import yaml
from rest_framework import serializers

from apps.core.utils.serializers import TeamSerializer
from apps.job_mgmt.models import Playbook


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

    filename = file.name.lower()
    file_content = file.read()
    file.seek(0)  # 重置文件指针，以便后续保存

    try:
        if filename.endswith(".zip"):
            result = _parse_zip(file_content)
        elif filename.endswith((".tar.gz", ".tgz")):
            result = _parse_tarball(file_content)
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


def _parse_zip(content: bytes) -> dict:
    """解析 ZIP 文件"""
    result = {"readme": "", "file_list": [], "params": []}
    paths = []

    with zipfile.ZipFile(io.BytesIO(content)) as zf:
        paths = zf.namelist()

        for name in zf.namelist():
            lower_name = name.lower()
            # 提取 README
            if lower_name.endswith("readme.md") or lower_name.endswith("readme.txt"):
                result["readme"] = zf.read(name).decode("utf-8", errors="ignore")
            # 提取参数（从 defaults/main.yml 或 vars/main.yml）
            elif lower_name.endswith(("defaults/main.yml", "defaults/main.yaml", "vars/main.yml", "vars/main.yaml")):
                params = _extract_params_from_yaml(zf.read(name))
                if params:
                    result["params"].extend(params)

    result["file_list"] = _build_file_tree(paths)
    return result


def _parse_tarball(content: bytes) -> dict:
    """解析 tar.gz/tgz 文件"""
    result = {"readme": "", "file_list": [], "params": []}
    paths = []

    with tarfile.open(fileobj=io.BytesIO(content), mode="r:gz") as tf:
        # 收集所有路径（文件和目录）
        for member in tf.getmembers():
            if member.isdir():
                paths.append(member.name + "/")
            else:
                paths.append(member.name)

        for member in tf.getmembers():
            if not member.isfile():
                continue
            lower_name = member.name.lower()
            # 提取 README
            if lower_name.endswith("readme.md") or lower_name.endswith("readme.txt"):
                f = tf.extractfile(member)
                if f:
                    result["readme"] = f.read().decode("utf-8", errors="ignore")
            # 提取参数
            elif lower_name.endswith(("defaults/main.yml", "defaults/main.yaml", "vars/main.yml", "vars/main.yaml")):
                f = tf.extractfile(member)
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


class PlaybookListSerializer(TeamSerializer):
    """Playbook列表序列化器（返回精简字段）"""

    class Meta:
        model = Playbook
        fields = [
            "id",
            "name",
            "version",
            "team_name",
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

        # 验证文件扩展名
        filename = value.name
        ext = os.path.splitext(filename)[1].lower()
        if ext not in [".zip", ".tar.gz", ".tgz"]:
            raise serializers.ValidationError("仅支持 .zip, .tar.gz, .tgz 格式的文件")

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

        # 创建 Playbook
        playbook = Playbook.objects.create(
            name=name,
            version=version,
            file=file,
            team=team,
            readme=parsed["readme"],
            file_list=parsed["file_list"],
            params=parsed["params"],
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

        filename = value.name
        ext = os.path.splitext(filename)[1].lower()
        if ext not in [".zip", ".tar.gz", ".tgz"]:
            raise serializers.ValidationError("仅支持 .zip, .tar.gz, .tgz 格式的文件")

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

        1. 上传新文件
        2. 解析 ZIP 包内容
        3. 更新版本号（自动或手动）
        4. 从文件名更新 name
        """
        file = validated_data["file"]
        new_version = validated_data.get("version", "").strip()

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

        # 更新实例
        instance.file = file
        instance.name = name
        instance.version = new_version
        instance.readme = parsed["readme"]
        instance.file_list = parsed["file_list"]
        instance.params = parsed["params"]
        instance.save()

        return instance


class PlaybookBatchDeleteSerializer(serializers.Serializer):
    """Playbook批量删除序列化器"""

    ids = serializers.ListField(child=serializers.IntegerField(), min_length=1, help_text="要删除的PlaybookID列表")
