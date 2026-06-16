"""零碎缺口补测：param_crypto / shell_utils / serializers / dangerous_checker / team_authz / validators / config"""

import pytest
from rest_framework import serializers as drf

from apps.core.mixinx import EncryptMixin
from apps.job_mgmt import config as job_config
from apps.job_mgmt.constants import DangerousLevel, JobType, MatchType, ScheduleType, TargetSource
from apps.job_mgmt.models import DangerousPath, Script
from apps.job_mgmt.serializers.script import ScriptCreateSerializer, ScriptSerializer, ScriptUpdateSerializer
from apps.job_mgmt.serializers.target import TargetSerializer
from apps.job_mgmt.serializers.validators import validate_scheduled_task_payload
from apps.job_mgmt.services.dangerous_checker import DangerousChecker
from apps.job_mgmt.services.param_crypto import ParamCrypto
from apps.job_mgmt.services.shell_utils import build_heredoc_command, parse_shebang


# ----------------------- ParamCrypto（纯，加解密）----------------------- #
class TestParamCrypto:
    def test_encrypt_and_mask_defaults(self):
        params = [{"name": "p", "default": "secret", "is_encrypted": True}, {"name": "q", "default": "plain"}]
        ParamCrypto.encrypt_param_defaults(params)
        assert params[0]["default"] != "secret"  # 已加密
        masked = ParamCrypto.mask_encrypted_defaults(params)
        assert masked[0]["default"] == "******"
        assert masked[1]["default"] == "plain"

    def test_encrypt_decrypt_execution_params_roundtrip(self):
        defs = [{"name": "pwd", "is_encrypted": True}]
        params = {"pwd": "s3cr3t"}
        ParamCrypto.encrypt_execution_params(params, defs)
        assert params["pwd"] != "s3cr3t"
        ParamCrypto.decrypt_execution_params(params, defs)
        assert params["pwd"] == "s3cr3t"

    def test_empty_inputs_passthrough(self):
        assert ParamCrypto.encrypt_param_defaults([]) == []
        assert ParamCrypto.mask_encrypted_defaults([]) == []
        assert ParamCrypto.encrypt_execution_params({}, []) == {}
        assert ParamCrypto.decrypt_execution_params({}, []) == {}
        assert ParamCrypto.decrypt_param_defaults([]) == []

    def test_prepare_params_for_execution(self):
        data = {"default": "v"}
        EncryptMixin.encrypt_field("default", data)
        defs = [{"name": "p1", "default": data["default"], "is_encrypted": True}, {"name": "p2", "default": "d2"}]
        result = ParamCrypto.prepare_params_for_execution({}, defs)
        assert result["p1"] == "v"  # 解密后填充
        assert result["p2"] == "d2"

    def test_prepare_no_definitions(self):
        assert ParamCrypto.prepare_params_for_execution({"a": 1}, []) == {"a": 1}


# ----------------------- shell_utils（纯）----------------------- #
class TestShellUtils:
    @pytest.mark.parametrize(
        "script,expected",
        [
            ("", None),
            ("echo hi", None),
            ("#!/bin/bash\necho", "bash"),
            ("#!/usr/bin/env python3\n", "python3"),
            ("#!\n", None),
            ("#!/bin/ruby\n", None),
        ],
    )
    def test_parse_shebang(self, script, expected):
        assert parse_shebang(script) == expected

    def test_build_heredoc(self):
        out = build_heredoc_command("python3", "print(1)")
        assert out.startswith("python3 <<") and "print(1)" in out


# ----------------------- dangerous_checker 别名 / 正则错误 ----------------------- #
@pytest.mark.django_db
class TestDangerousCheckerExtra:
    def test_check_script_alias(self):
        assert DangerousChecker.check_script("echo", [1]).can_execute is True

    def test_check_file_distribution_alias(self):
        assert DangerousChecker.check_file_distribution("/tmp", [1]).can_execute is True

    def test_check_path_invalid_regex_does_not_crash(self):
        DangerousPath.objects.create(
            name="bad", pattern="[unclosed", match_type=MatchType.REGEX, level=DangerousLevel.FORBIDDEN, is_enabled=True, team=[]
        )
        # 非法正则被吞掉并记录告警，整体不抛、可执行
        assert DangerousChecker.check_path("/tmp/x", [1]).can_execute is True


# ----------------------- team_authz 边界 ----------------------- #
class TestTeamAuthzEdges:
    def test_normalize_team_skips_non_int(self):
        from apps.job_mgmt.utils.team_authz import normalize_team

        assert normalize_team([1, "x", 2, None]) == {1, 2}

    def test_normalize_authorized_skips_bad_group(self):
        from apps.job_mgmt.utils.team_authz import normalize_authorized_team_ids

        assert normalize_authorized_team_ids([{"id": 1}, {"id": "bad"}, {"noid": 9}]) == {1}


# ----------------------- serializers/script 校验 + mask ----------------------- #
@pytest.mark.django_db
class TestScriptSerializer:
    def test_to_representation_masks_encrypted(self):
        s = Script.objects.create(
            name="s", content="echo", script_type="shell", team=[1], params=[{"name": "p", "default": "x", "is_encrypted": True}]
        )
        data = ScriptSerializer(s).data
        assert data["params"][0]["default"] == "******"

    def test_create_serializer_rejects_empty_content(self):
        s = ScriptCreateSerializer(data={"name": "x", "content": "  ", "script_type": "shell", "team": [1]})
        assert not s.is_valid()
        assert "content" in s.errors

    def test_create_serializer_rejects_empty_team(self):
        s = ScriptCreateSerializer(data={"name": "x", "content": "echo", "script_type": "shell", "team": []})
        assert not s.is_valid()
        assert "team" in s.errors

    def test_update_serializer_rejects_blank_content(self):
        s = ScriptUpdateSerializer(data={"content": "   ", "team": [1]}, partial=True)
        assert not s.is_valid()


# ----------------------- serializers/target validate_team + region ----------------------- #
def _ts(instance=None):
    """TargetSerializer 需要 context['request'].user.group_list（TeamSerializer 基类）。"""
    from types import SimpleNamespace

    req = SimpleNamespace(user=SimpleNamespace(group_list=[{"id": 1, "name": "T1"}]))
    return TargetSerializer(instance, context={"request": req})


@pytest.mark.django_db
class TestTargetSerializer:
    @pytest.mark.parametrize("value,expected", [(None, []), (5, [5]), ([1, 2], [1, 2])])
    def test_validate_team_normalizes(self, value, expected):
        assert _ts().validate_team(value) == expected

    def test_validate_team_invalid_raises(self):
        with pytest.raises(drf.ValidationError):
            _ts().validate_team("bad")

    def test_get_cloud_region_name_none(self):
        from apps.job_mgmt.models import Target

        t = Target.objects.create(name="t", ip="10.0.0.1", ssh_user="r", team=[1], cloud_region_id=None)
        assert _ts().get_cloud_region_name(t) is None

    def test_serialize_triggers_region_map(self):
        from apps.job_mgmt.models import Target

        t = Target.objects.create(name="t", ip="10.0.0.1", ssh_user="r", team=[1], cloud_region_id=999)
        data = _ts(t).data  # 触发 cached_property cloud_region_map
        assert data["cloud_region_name"] is None  # 测试库无该区域


# ----------------------- validators 定时任务 manual 目标校验 ----------------------- #
@pytest.mark.django_db
class TestScheduledValidatorDbBranch:
    def test_manual_target_not_exist_raises(self):
        attrs = {
            "schedule_type": ScheduleType.CRON,
            "cron_expression": "* * * * *",
            "job_type": JobType.SCRIPT,
            "script_content": "echo",
            "script_type": "shell",
            "target_source": TargetSource.MANUAL,
            "target_list": [{"target_id": 999999}],
        }
        with pytest.raises(drf.ValidationError):
            validate_scheduled_task_payload(attrs, instance=None)

    def test_valid_params_format_passes(self):
        attrs = {
            "schedule_type": ScheduleType.CRON,
            "cron_expression": "* * * * *",
            "job_type": JobType.SCRIPT,
            "script_content": "echo",
            "script_type": "shell",
            "target_source": TargetSource.NODE_MGMT,
            "target_list": [{"node_id": "n1"}],
            "params": [{"name": "p", "value": "v", "is_modified": True}],
        }
        assert validate_scheduled_task_payload(attrs, instance=None) is attrs


# ----------------------- config._int_env ----------------------- #
class TestConfigIntEnv:
    def test_invalid_env_returns_default(self, monkeypatch):
        monkeypatch.setenv("JOB_TEST_INT", "not-a-number")
        assert job_config._int_env("JOB_TEST_INT", 7) == 7

    def test_valid_env(self, monkeypatch):
        monkeypatch.setenv("JOB_TEST_INT", "42")
        assert job_config._int_env("JOB_TEST_INT", 7) == 42
