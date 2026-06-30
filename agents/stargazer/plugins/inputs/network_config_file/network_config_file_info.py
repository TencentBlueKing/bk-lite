import re

from plugins.inputs.network_config_file.constants import DANGEROUS_COMMAND_PREFIXES, DANGEROUS_EXACT_COMMANDS


def validate_safe_command(command: str) -> str:
    normalized = " ".join(str(command or "").strip().split())
    lowered = normalized.lower()
    if not lowered:
        raise ValueError("采集命令不能为空")
    if lowered in DANGEROUS_EXACT_COMMANDS:
        raise ValueError(f"采集命令存在高危操作: {normalized}")
    first_word = re.split(r"\s+", lowered, maxsplit=1)[0]
    if first_word in DANGEROUS_COMMAND_PREFIXES:
        raise ValueError(f"采集命令存在高危操作: {normalized}")
    return normalized


class NetworkConfigFileInfo:
    @staticmethod
    def merge_command_outputs(results: list[dict]) -> str:
        sections = []
        for item in results:
            sections.append(f"===== command: {item.get('command', '')} =====\n{item.get('output', '')}")
        return "\n\n".join(sections)
