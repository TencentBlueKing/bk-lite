import re
from dataclasses import dataclass
from enum import Enum

import toml

MANAGED_BLOCK_BEGIN = "# bk-lite:vector-host-metadata:v1 begin"
MANAGED_BLOCK_END = "# bk-lite:vector-host-metadata:v1 end"
MANAGED_BLOCK = (
    f"{MANAGED_BLOCK_BEGIN}\n"
    '.host_name = decode_base64!("${node.name_b64}")\n'
    '.host_ip = decode_base64!("${node.ip_b64}")\n'
    f"{MANAGED_BLOCK_END}\n"
)
HOST_ASSIGNMENT_PATTERN = re.compile(r"(?<![\w.])\.(host_name|host_ip)\s*=")
MANAGED_MARKER_PATTERN = re.compile(r"(?m)^\s*#\s*bk-lite:vector-host-metadata:[^\r\n]*$")


class PatchState(str, Enum):
    ABSENT = "absent"
    CURRENT = "current"
    MANAGED_DRIFT = "managed_drift"
    UNMANAGED_CONFLICT = "unmanaged_conflict"
    INVALID = "invalid"


@dataclass(frozen=True)
class PatchResult:
    state: PatchState
    content: str
    changed: bool = False
    reason: str = ""


@dataclass(frozen=True)
class _TargetTransform:
    name: str
    source: str
    source_start: int
    source_end: int


class VectorHostMetadataPatch:
    """Inspect and patch the owned Vector host-metadata block without rewriting TOML."""

    @classmethod
    def inspect(cls, content: str, *, collect_type: str, config_id: str, instance_id: str) -> PatchResult:
        try:
            target = cls._find_target(content, collect_type=collect_type, config_id=config_id, instance_id=instance_id)
            source = target.source
            markers = MANAGED_MARKER_PATTERN.findall(source)
            begin_count = source.count(MANAGED_BLOCK_BEGIN)
            end_count = source.count(MANAGED_BLOCK_END)
            assignment_count = len(HOST_ASSIGNMENT_PATTERN.findall(source))

            if not markers:
                if assignment_count:
                    return PatchResult(PatchState.UNMANAGED_CONFLICT, content, reason="unmanaged host metadata assignment")
                return PatchResult(PatchState.ABSENT, content)

            if (
                len(markers) != 2
                or begin_count != 1
                or end_count != 1
                or {marker.strip() for marker in markers} != {MANAGED_BLOCK_BEGIN, MANAGED_BLOCK_END}
            ):
                return PatchResult(PatchState.INVALID, content, reason="invalid or unknown managed markers")

            begin_index = source.find(MANAGED_BLOCK_BEGIN)
            end_marker_index = source.find(MANAGED_BLOCK_END)
            if begin_index < 0 or end_marker_index < begin_index:
                return PatchResult(PatchState.INVALID, content, reason="managed markers are out of order")
            end_index = end_marker_index + len(MANAGED_BLOCK_END)
            block_end = end_index + (1 if source[end_index : end_index + 1] == "\n" else 0)
            managed_block = source[begin_index:block_end]
            outside = source[:begin_index] + source[block_end:]
            if HOST_ASSIGNMENT_PATTERN.search(outside):
                return PatchResult(PatchState.UNMANAGED_CONFLICT, content, reason="host metadata assignment outside managed block")
            if managed_block == MANAGED_BLOCK:
                return PatchResult(PatchState.CURRENT, content)
            return PatchResult(PatchState.MANAGED_DRIFT, content, reason="managed block differs from v1")
        except (TypeError, ValueError, toml.TomlDecodeError) as exc:
            return PatchResult(PatchState.INVALID, content, reason=str(exc))

    @classmethod
    def apply(cls, content: str, *, collect_type: str, config_id: str, instance_id: str) -> PatchResult:
        inspection = cls.inspect(content, collect_type=collect_type, config_id=config_id, instance_id=instance_id)
        if inspection.state in {PatchState.CURRENT, PatchState.UNMANAGED_CONFLICT, PatchState.INVALID}:
            return inspection

        try:
            target = cls._find_target(content, collect_type=collect_type, config_id=config_id, instance_id=instance_id)
            if inspection.state is PatchState.ABSENT:
                updated_source = target.source + MANAGED_BLOCK
            else:
                updated_source = cls._replace_managed_block(target.source, MANAGED_BLOCK)
            updated = content[: target.source_start] + updated_source + content[target.source_end :]
            cls._validate_only_target_source_changed(content, updated, target.name)
        except (TypeError, ValueError, toml.TomlDecodeError) as exc:
            return PatchResult(PatchState.INVALID, content, reason=str(exc))
        final = cls.inspect(updated, collect_type=collect_type, config_id=config_id, instance_id=instance_id)
        if final.state is not PatchState.CURRENT:
            return PatchResult(PatchState.INVALID, content, reason="patched content did not reach current state")
        return PatchResult(PatchState.CURRENT, updated, changed=True)

    @classmethod
    def revert(cls, content: str, *, collect_type: str, config_id: str, instance_id: str) -> PatchResult:
        inspection = cls.inspect(content, collect_type=collect_type, config_id=config_id, instance_id=instance_id)
        if inspection.state is PatchState.ABSENT:
            return inspection
        if inspection.state is not PatchState.CURRENT:
            return inspection

        try:
            target = cls._find_target(content, collect_type=collect_type, config_id=config_id, instance_id=instance_id)
            updated_source = target.source.replace(MANAGED_BLOCK, "", 1)
            updated = content[: target.source_start] + updated_source + content[target.source_end :]
            cls._validate_only_target_source_changed(content, updated, target.name)
        except (TypeError, ValueError, toml.TomlDecodeError) as exc:
            return PatchResult(PatchState.INVALID, content, reason=str(exc))
        final = cls.inspect(updated, collect_type=collect_type, config_id=config_id, instance_id=instance_id)
        if final.state is not PatchState.ABSENT:
            return PatchResult(PatchState.INVALID, content, reason="reverted content did not reach absent state")
        return PatchResult(PatchState.ABSENT, updated, changed=True)

    @staticmethod
    def _expected_names(collect_type: str, config_id: str, instance_id: str) -> tuple[str, str, tuple[str, ...]]:
        if collect_type == "file":
            suffix = str(config_id).lower().replace("-", "_")
            return f"file_enrich_{suffix}", f"vmlogs_{suffix}", (f"file_{suffix}", f"file_parse_{suffix}")
        if collect_type == "docker":
            suffix = str(instance_id)
            return f"docker_enrich_{suffix}", f"vmlogs_{suffix}", (f"docker_{suffix}",)
        raise ValueError(f"unsupported collect type: {collect_type}")

    @classmethod
    def _find_target(cls, content: str, *, collect_type: str, config_id: str, instance_id: str) -> _TargetTransform:
        if not isinstance(content, str) or not content:
            raise ValueError("child config content is empty")
        parsed = toml.loads(content)
        expected_transform, expected_sink, expected_inputs = cls._expected_names(collect_type, config_id, instance_id)
        sources = parsed.get("sources")
        transforms = parsed.get("transforms")
        sinks = parsed.get("sinks")
        if not isinstance(sources, dict) or not isinstance(transforms, dict) or not isinstance(sinks, dict):
            raise ValueError("missing sources, transforms, or sinks")
        enrich_names = [name for name in transforms if name.startswith(f"{collect_type}_enrich_")]
        if enrich_names != [expected_transform]:
            raise ValueError("missing or ambiguous enrich transform")
        transform = transforms[expected_transform]
        if not isinstance(transform, dict) or transform.get("type") != "remap" or not isinstance(transform.get("source"), str):
            raise ValueError("invalid enrich transform")
        inputs = transform.get("inputs")
        if not isinstance(inputs, list) or len(inputs) != 1 or inputs[0] not in expected_inputs:
            raise ValueError("invalid enrich input")
        cls._validate_enrich_input_topology(sources, transforms, collect_type, inputs[0], expected_inputs[0])
        sink = sinks.get(expected_sink)
        if not isinstance(sink, dict) or sink.get("type") != "nats" or sink.get("inputs") != [expected_transform]:
            raise ValueError("invalid Vector NATS sink topology")
        source = transform["source"]
        if not source.endswith("\n"):
            raise ValueError("enrich source must end with a newline")
        cls._validate_identity_assignment(source, "collector", "Vector")
        cls._validate_identity_assignment(source, "collect_type", collect_type)
        cls._validate_identity_assignment(source, "instance_id", str(instance_id))
        if collect_type == "file":
            cls._validate_identity_assignment(source, "config_id", str(config_id), case_sensitive=False)

        table_pattern = re.compile(rf"(?m)^\[transforms\.{re.escape(expected_transform)}\]\s*$")
        table_match = table_pattern.search(content)
        if not table_match:
            raise ValueError("target transform table not found in raw content")
        next_table_match = re.search(r"(?m)^\[", content[table_match.end() :])
        section_end = table_match.end() + next_table_match.start() if next_table_match else len(content)
        section = content[table_match.end() : section_end]
        source_matches = list(re.finditer(r"(?ms)^source\s*=\s*'''\n(.*?)'''\s*$", section))
        if len(source_matches) != 1:
            raise ValueError("target source is not a unique triple-single-quoted block")
        source_match = source_matches[0]
        source_start = table_match.end() + source_match.start(1)
        source_end = table_match.end() + source_match.end(1)
        raw_source = content[source_start:source_end]
        if raw_source != source:
            raise ValueError("raw and parsed enrich source differ")
        return _TargetTransform(expected_transform, source, source_start, source_end)

    @staticmethod
    def _validate_enrich_input_topology(sources: dict, transforms: dict, collect_type: str, input_name: str, source_name: str) -> None:
        source = sources.get(source_name)
        expected_source_type = "file" if collect_type == "file" else "docker_logs"
        if not isinstance(source, dict) or source.get("type") != expected_source_type:
            raise ValueError("invalid Vector source topology")
        if input_name == source_name:
            return
        parser = transforms.get(input_name)
        if (
            collect_type != "file"
            or not isinstance(parser, dict)
            or parser.get("type") != "remap"
            or parser.get("inputs") != [source_name]
            or not isinstance(parser.get("source"), str)
        ):
            raise ValueError("invalid file parser topology")

    @staticmethod
    def _validate_identity_assignment(source: str, field: str, expected: str, *, case_sensitive: bool = True) -> None:
        matches = re.findall(rf'(?m)^\s*\.{re.escape(field)}\s*=\s*"([^"\r\n]*)"\s*$', source)
        if len(matches) != 1:
            raise ValueError(f"invalid {field} identity assignment")
        actual = matches[0]
        if case_sensitive:
            matches_expected = actual == expected
        else:
            matches_expected = actual.casefold() == expected.casefold()
        if not matches_expected:
            raise ValueError(f"mismatched {field} identity assignment")

    @staticmethod
    def _replace_managed_block(source: str, replacement: str) -> str:
        begin_index = source.index(MANAGED_BLOCK_BEGIN)
        end_index = source.index(MANAGED_BLOCK_END, begin_index) + len(MANAGED_BLOCK_END)
        block_end = end_index + (1 if source[end_index : end_index + 1] == "\n" else 0)
        return source[:begin_index] + replacement + source[block_end:]

    @staticmethod
    def _validate_only_target_source_changed(original: str, updated: str, transform_name: str) -> None:
        before = toml.loads(original)
        after = toml.loads(updated)
        before_source = before["transforms"][transform_name].pop("source")
        after_source = after["transforms"][transform_name].pop("source")
        if before != after or not isinstance(before_source, str) or not isinstance(after_source, str):
            raise ValueError("patch changed content outside the target enrich source")
