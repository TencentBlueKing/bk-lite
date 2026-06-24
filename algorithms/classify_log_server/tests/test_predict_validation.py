"""
回归测试：确保 predict 端点签名使用 LogClusterRequest，
激活 max_length=10000 和单条 10KB 大小校验。

Issue #3534：predict 签名原为裸 list[str]，导致 LogClusterRequest 校验形同虚设。

测试验证原则（revert-fail 准则）：
若将 predict 签名改回 list[str]，以下测试必须失败——
因为裸 list[str] 不会触发 Pydantic 的 max_length / field_validator。
"""

import importlib
import inspect
import sys
import types


def _install(name: str, **attrs):
    """向 sys.modules 注入伪模块，避免在无外部依赖环境中 ImportError。"""
    mod = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(mod, k, v)
    sys.modules[name] = mod
    return mod


def _load(module_name: str, file_path: str):
    """按文件路径加载模块，绕开包 __init__ 链。"""
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


def _setup_stubs():
    """注入所有外部依赖的最小桩，使 service.py 可以被 import。"""
    import pathlib

    # pydantic 真实可用，无需桩
    from pydantic import BaseModel, Field, field_validator
    from typing import List, Optional, Any, Dict

    # ---- bentoml 桩 ----
    bentoml_mod = _install("bentoml")

    def _api(fn=None, **kw):
        """bentoml.api 装饰器桩：直接返回原函数。"""
        if fn is not None:
            return fn
        return lambda f: f

    def _service(name=None, **kw):
        return lambda cls: cls

    def _on_deployment(fn):
        return fn

    def _on_shutdown(fn):
        return fn

    bentoml_mod.api = _api
    bentoml_mod.service = _service
    bentoml_mod.on_deployment = _on_deployment
    bentoml_mod.on_shutdown = _on_shutdown

    # ---- loguru 桩 ----
    logger_stub = types.SimpleNamespace(
        info=lambda *a, **k: None,
        error=lambda *a, **k: None,
        warning=lambda *a, **k: None,
        debug=lambda *a, **k: None,
    )
    loguru_mod = _install("loguru")
    loguru_mod.logger = logger_stub

    # ---- prometheus_client 桩 ----
    class _Counter:
        def labels(self, **kw):
            return self
        def inc(self, *a):
            pass

    prom_mod = _install("prometheus_client")
    prom_mod.Counter = lambda *a, **k: _Counter()
    prom_mod.Histogram = lambda *a, **k: _Counter()
    prom_mod.Gauge = lambda *a, **k: _Counter()

    # ---- pandas 桩（仅用于类型，实际路径不走 predict 推理逻辑）----
    _install("pandas")

    # ---- 服务内部子模块桩 ----
    serving_base = "classify_log_server.serving"

    # config
    cfg_mod = _install(f"{serving_base}.config")
    cfg_mod.get_model_config = lambda: types.SimpleNamespace(source="stub")

    # exceptions
    exc_mod = _install(f"{serving_base}.exceptions")
    exc_mod.ModelInferenceError = Exception

    # metrics
    m_mod = _install(f"{serving_base}.metrics")
    _stub_counter = _Counter()
    m_mod.health_check_counter = _stub_counter
    m_mod.model_load_counter = _stub_counter
    m_mod.prediction_counter = _stub_counter
    m_mod.prediction_duration = _stub_counter

    # models
    mdl_mod = _install(f"{serving_base}.models")
    mdl_mod.load_model = lambda cfg: types.SimpleNamespace()

    # ---- 加载真实 api_schema（依赖 pydantic，无外部 IO）----
    base_dir = pathlib.Path(__file__).parent.parent / "classify_log_server" / "serving"
    api_schema = _load(f"{serving_base}.schemas.api_schema", str(base_dir / "schemas" / "api_schema.py"))

    # schemas __init__
    schemas_mod = _install(f"{serving_base}.schemas")
    for name in [
        "LogClusterRequest", "LogClusterConfig", "LogClusterResponseV2",
        "LogClusterResult", "TemplateGroup", "ClusteringSummary",
    ]:
        setattr(schemas_mod, name, getattr(api_schema, name))

    # ---- 加载真实 service.py ----
    service_mod = _load(f"{serving_base}.service", str(base_dir / "service.py"))
    return service_mod, api_schema


# ========== 加载被测模块 ==========
_service_mod, _api_schema = _setup_stubs()
MLService = _service_mod.MLService
LogClusterRequest = _api_schema.LogClusterRequest
LogClusterConfig = _api_schema.LogClusterConfig


# ========== 测试：签名级校验（revert-fail 关键测试）==========

class TestPredictSignatureUsesLogClusterRequest:
    """
    确认 predict 方法的第一个（非 self）参数类型注解为 LogClusterRequest。

    若签名被改回 list[str]，本测试必须失败——这正是 revert-fail 准则的体现。
    """

    def test_predict_first_param_is_log_cluster_request(self):
        """predict 的第一个参数类型注解必须是 LogClusterRequest。"""
        sig = inspect.signature(MLService.predict)
        params = [p for name, p in sig.parameters.items() if name != "self"]
        assert len(params) >= 1, "predict 必须有至少一个非 self 参数"
        first_param = params[0]
        assert first_param.annotation is LogClusterRequest, (
            f"predict 第一个参数注解应为 LogClusterRequest，实际为 {first_param.annotation}。"
            f"\n这意味着 issue #3534 的修复已被回退——BentoML 将绕过 max_length 和 field_validator 校验。"
        )

    def test_predict_does_not_accept_bare_list_as_first_param(self):
        """predict 第一个参数不得是裸 list[str]（确保校验不被绕过）。"""
        sig = inspect.signature(MLService.predict)
        params = [p for name, p in sig.parameters.items() if name != "self"]
        assert len(params) >= 1
        first_param = params[0]
        # list[str] 在 Python 中是 list 的泛型别名，annotation != list 且 != list[str]
        import typing
        bare_list_annotations = (list, typing.List)
        # get_origin 检测泛型
        origin = getattr(first_param.annotation, "__origin__", None)
        assert origin is not list, (
            "predict 第一个参数不得是 list[str] 等裸列表类型——这会绕过 LogClusterRequest 的输入校验。"
        )


# ========== 测试：LogClusterRequest Pydantic 校验本身正确 ==========

class TestLogClusterRequestValidation:
    """
    确认 LogClusterRequest 的校验规则在被 predict 接收时实际生效。

    这些测试在"修复后"通过，在"修复前"（签名为 list[str]）无意义——
    因为 BentoML 不会通过 LogClusterRequest 反序列化，校验从不触发。
    """

    def test_valid_request_passes(self):
        """正常请求通过校验。"""
        req = LogClusterRequest(data=["log line 1", "log line 2"])
        assert len(req.data) == 2

    def test_max_length_10000_enforced(self):
        """超过 10000 条日志时，LogClusterRequest 应拒绝（触发 ValidationError）。"""
        from pydantic import ValidationError
        oversized = ["x"] * 10001
        try:
            LogClusterRequest(data=oversized)
            raise AssertionError(
                "应抛出 ValidationError，但未抛出。"
                "这说明 LogClusterRequest 的 max_length=10000 校验未生效。"
            )
        except ValidationError as e:
            # 确认是 max_length 相关错误
            errors = e.errors()
            assert any("max_length" in str(err) or "too_long" in str(err.get("type", "")) for err in errors), (
                f"ValidationError 应包含 max_length 相关错误，实际错误：{errors}"
            )

    def test_single_log_over_10kb_rejected(self):
        """单条日志超过 10KB 时，field_validator 应拒绝。"""
        from pydantic import ValidationError
        # 生成一条超过 10KB 的日志（10 * 1024 + 1 字节）
        oversized_log = "A" * (10 * 1024 + 1)
        try:
            LogClusterRequest(data=[oversized_log])
            raise AssertionError(
                "应抛出 ValidationError，但未抛出。"
                "这说明 LogClusterRequest 的单条 10KB field_validator 未生效。"
            )
        except ValidationError as e:
            errors = e.errors()
            assert any("大小超过限制" in str(err.get("msg", "")) or "超过" in str(err.get("msg", "")) for err in errors), (
                f"ValidationError 应包含大小限制相关错误，实际错误：{errors}"
            )

    def test_empty_data_rejected(self):
        """空列表应被 min_length=1 拒绝。"""
        from pydantic import ValidationError
        try:
            LogClusterRequest(data=[])
            raise AssertionError("应抛出 ValidationError（空列表），但未抛出。")
        except ValidationError:
            pass  # 预期

    def test_config_defaults_applied(self):
        """LogClusterRequest 的 config 字段有正确默认值。"""
        req = LogClusterRequest(data=["test log"])
        assert req.config.return_details is False
        assert req.config.max_samples == 5
        assert req.config.sort_by == "count"
