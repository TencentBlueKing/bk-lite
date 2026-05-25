import json
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand

from apps.core.logger import mlops_logger as logger
from apps.mlops.models import AlgorithmConfig


class Command(BaseCommand):
    help = "初始化 MLOPS 算法配置"

    def handle(self, *args, **options):
        config_root = Path(__file__).resolve().parents[2] / "support-files" / "algorithm-configs"
        allowed_types = {value for value, _ in AlgorithmConfig.ALGORITHM_TYPE_CHOICES}

        created_count = 0
        skipped_existing_count = 0
        skipped_invalid_count = 0

        self.stdout.write("开始初始化 MLOPS 算法配置")
        logger.info("开始初始化 MLOPS 算法配置: %s", config_root)

        if not config_root.exists():
            self.stdout.write(f"未找到算法配置目录: {config_root}")
            logger.warning("未找到算法配置目录: %s", config_root)
            self._write_summary(created_count, skipped_existing_count, skipped_invalid_count)
            return

        for algorithm_type_dir in sorted(config_root.iterdir()):
            if not algorithm_type_dir.is_dir():
                continue

            if algorithm_type_dir.name not in allowed_types:
                continue

            for config_file in sorted(algorithm_type_dir.iterdir()):
                if not config_file.is_file() or config_file.suffix.lower() != ".json":
                    continue

                valid, payload, reason = self._load_and_validate_file(config_file)
                if not valid:
                    skipped_invalid_count += 1
                    self._report_invalid(config_file, reason)
                    continue

                manager = AlgorithmConfig.objects
                _, created = manager.get_or_create(
                    algorithm_type=algorithm_type_dir.name,
                    name=payload["name"],
                    defaults={
                        "display_name": payload["display_name"],
                        "image": payload["image"],
                        "scenario_description": payload["scenario_description"],
                        "form_config": payload["form_config"],
                    },
                )

                if created:
                    created_count += 1
                    self.stdout.write(f"已创建: {algorithm_type_dir.name}/{payload['name']}")
                    logger.info("已创建: %s/%s", algorithm_type_dir.name, payload["name"])
                    continue

                skipped_existing_count += 1
                self.stdout.write(f"已存在，跳过: {algorithm_type_dir.name}/{payload['name']}")
                logger.info("已存在，跳过: %s/%s", algorithm_type_dir.name, payload["name"])

        self._write_summary(created_count, skipped_existing_count, skipped_invalid_count)

    def _load_and_validate_file(self, config_file: Path) -> tuple[bool, dict[str, Any], str]:
        try:
            payload: Any = json.loads(config_file.read_text(encoding="utf-8"))
        except Exception as exc:
            return False, {}, f"JSON 解析失败: {exc}"

        if not isinstance(payload, dict):
            return False, {}, "顶层必须是对象"

        required_fields = {"name", "display_name", "image", "scenario_description", "form_config"}
        payload_keys = set(payload.keys())
        if payload_keys != required_fields:
            missing = sorted(required_fields - payload_keys)
            extra = sorted(payload_keys - required_fields)
            details = []
            if missing:
                details.append(f"缺少字段: {', '.join(missing)}")
            if extra:
                details.append(f"多余字段: {', '.join(extra)}")
            return False, {}, "; ".join(details) if details else "顶层字段不符合约束"

        if not isinstance(payload["form_config"], dict):
            return False, {}, "form_config 必须是对象"

        for field_name in ("name", "display_name", "image", "scenario_description"):
            if not isinstance(payload[field_name], str):
                return False, {}, f"{field_name} 必须是字符串"

            if field_name != "scenario_description" and not payload[field_name].strip():
                return False, {}, f"{field_name} 不能为空字符串"

        if payload["name"] != config_file.stem:
            return False, {}, "name 必须与文件名 stem 完全一致"

        return True, payload, ""

    def _report_invalid(self, config_file: Path, reason: str):
        message = f"无效配置: {config_file}，原因: {reason}"
        self.stderr.write(message)

    def _write_summary(self, created_count: int, skipped_existing_count: int, skipped_invalid_count: int):
        summary = (
            f"初始化完成: created={created_count}, "
            f"skipped_existing={skipped_existing_count}, skipped_invalid={skipped_invalid_count}"
        )
        self.stdout.write(summary)
        logger.info(summary)
