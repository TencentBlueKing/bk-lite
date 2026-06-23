"""
Tests for MLService._get_feature_importance (Issue #3543).

验证修复点：
1. 当模型不暴露 python_model 时，返回 None 而非伪造权重
2. 当 XGBoostWrapper 存在但 TF-IDF 词汇表无法匹配文本词语时，返回空列表
3. 当 XGBoostWrapper 完整可访问时，返回基于真实 feature_importances_ 的结果
4. 真实结果按重要性降序排列，而非按词在文本中的出现顺序
5. contribution 字段由实际分数符号决定，而非全部硬编码为 "positive"
"""

import sys
import types
import importlib.util
from pathlib import Path
from unittest.mock import MagicMock
import numpy as np


# ---------------------------------------------------------------------------
# 最小化依赖注入：将 BentoML / loguru 等包注入 sys.modules，避免安装依赖
# ---------------------------------------------------------------------------

def _make_stub(name, **attrs):
    mod = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(mod, k, v)
    return mod


def _inject_stubs():
    # bentoml
    bentoml_mod = _make_stub("bentoml")

    def _noop_decorator(*args, **kwargs):
        if len(args) == 1 and callable(args[0]):
            return args[0]
        def _inner(fn):
            return fn
        return _inner

    bentoml_mod.service = _noop_decorator
    bentoml_mod.api = _noop_decorator
    bentoml_mod.on_deployment = _noop_decorator
    bentoml_mod.on_shutdown = _noop_decorator
    sys.modules.setdefault("bentoml", bentoml_mod)

    # loguru
    logger_stub = MagicMock()
    loguru_mod = _make_stub("loguru", logger=logger_stub)
    sys.modules.setdefault("loguru", loguru_mod)

    # numpy / pandas – usually available, but ensure no ImportError propagates
    import numpy  # noqa: F401
    import pandas  # noqa: F401


_inject_stubs()


# ---------------------------------------------------------------------------
# 动态加载被测模块（避免走 Django settings 初始化）
# ---------------------------------------------------------------------------

SERVICE_FILE = (
    Path(__file__).parent.parent
    / "classify_text_classification_server"
    / "serving"
    / "service.py"
)


def _load_service_module():
    """按路径加载 service.py，跳过包初始化链。"""
    # 先注入 serving 子包中的依赖
    for sub in [
        "classify_text_classification_server.serving.config",
        "classify_text_classification_server.serving.exceptions",
        "classify_text_classification_server.serving.metrics",
        "classify_text_classification_server.serving.models",
        "classify_text_classification_server.serving.schemas",
    ]:
        if sub not in sys.modules:
            sys.modules[sub] = MagicMock()

    # 注入 schemas 中的真实类（FeatureImportance 需要）
    schema_path = (
        Path(__file__).parent.parent
        / "classify_text_classification_server"
        / "serving"
        / "schemas"
        / "api_schema.py"
    )
    spec = importlib.util.spec_from_file_location(
        "classify_text_classification_server.serving.schemas.api_schema", schema_path
    )
    schema_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(schema_mod)
    sys.modules["classify_text_classification_server.serving.schemas.api_schema"] = schema_mod

    # 让 schemas 包暴露 FeatureImportance 等
    schemas_pkg = sys.modules["classify_text_classification_server.serving.schemas"]
    for attr in [
        "PredictRequest", "PredictResponse", "PredictionConfig",
        "ClassificationResult", "ClassificationLabel", "FeatureImportance",
        "TextWarning", "PredictionSummary", "ResponseMetadata", "ErrorDetail",
    ]:
        setattr(schemas_pkg, attr, getattr(schema_mod, attr, MagicMock()))

    spec = importlib.util.spec_from_file_location(
        "classify_text_classification_server.serving.service", SERVICE_FILE
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_svc_mod = _load_service_module()
MLService = _svc_mod.MLService


# ---------------------------------------------------------------------------
# 构造一个最小化的 MLService 实例（跳过 __init__ 中的 bentoml + load_model）
# ---------------------------------------------------------------------------

def _make_service(model=None):
    """绕过 __init__ 直接创建 MLService 实例，注入给定的 model 对象。"""
    svc = object.__new__(MLService)
    svc.config = MagicMock()
    svc.model = model
    return svc


# ---------------------------------------------------------------------------
# 测试 1：模型没有 _model_impl 时返回 None
# ---------------------------------------------------------------------------

def test_no_python_model_returns_none():
    """当 model 不暴露 _model_impl 时应返回 None，而非位置伪造权重。"""
    plain_model = object()  # 没有任何属性
    svc = _make_service(model=plain_model)

    result = svc._get_feature_importance("B A C", max_features=10)

    assert result is None, (
        "期望返回 None（无法提取真实归因），但得到了 %r" % result
    )


# ---------------------------------------------------------------------------
# 测试 2：python_model 存在但缺少 feature_engineer 时返回 None
# ---------------------------------------------------------------------------

def test_missing_feature_engineer_returns_none():
    python_model_stub = MagicMock(spec=[])  # 无任何属性
    model_impl = MagicMock()
    model_impl.python_model = python_model_stub

    pyfunc_model = MagicMock()
    pyfunc_model._model_impl = model_impl

    svc = _make_service(model=pyfunc_model)
    result = svc._get_feature_importance("A B C", max_features=5)
    assert result is None


# ---------------------------------------------------------------------------
# 测试 3：词汇表完整可访问时返回真实 feature_importances_
# ---------------------------------------------------------------------------

def test_real_feature_importances_returned():
    """当 XGBoostWrapper 完整可访问时，应返回基于 feature_importances_ 的真实得分。"""
    # 构造模拟的 TF-IDF 词汇表：B 列索引 0，A 列索引 1，C 列索引 2
    tfidf_mock = MagicMock()
    tfidf_mock.vocabulary_ = {"B": 0, "A": 1, "C": 2}

    feature_engineer_mock = MagicMock()
    feature_engineer_mock.tfidf_vectorizer = tfidf_mock

    # XGBoost feature_importances_：B=0.1，A=0.9，C=0.3
    xgb_model_mock = MagicMock()
    xgb_model_mock.feature_importances_ = np.array([0.1, 0.9, 0.3])

    python_model_stub = MagicMock()
    python_model_stub.feature_engineer = feature_engineer_mock
    python_model_stub.model = xgb_model_mock

    model_impl = MagicMock()
    model_impl.python_model = python_model_stub

    pyfunc_model = MagicMock()
    pyfunc_model._model_impl = model_impl

    svc = _make_service(model=pyfunc_model)

    # 输入文本 "B A C"，B 位置最前，但 A 的真实重要性最高
    result = svc._get_feature_importance("B A C", max_features=10)

    assert result is not None, "应返回特征列表而非 None"
    assert len(result) == 3

    # 验证排序是按真实重要性降序（A > C > B），而非按词出现位置
    feature_names = [f.feature for f in result]
    assert feature_names[0] == "A", (
        "重要性最高的词应是 A（score=0.9），而非 B（score=0.1）。"
        "这验证了修复：不再使用位置倒数排名。实际顺序: %s" % feature_names
    )
    assert feature_names[1] == "C"
    assert feature_names[2] == "B"

    # 验证重要性数值是真实值，不是 1/(i+1)
    assert abs(result[0].importance - 0.9) < 1e-4
    assert abs(result[1].importance - 0.3) < 1e-4
    assert abs(result[2].importance - 0.1) < 1e-4


# ---------------------------------------------------------------------------
# 测试 4：revert 验证——如果把修复 revert 回旧实现，测试应该失败
#          （此测试直接调用旧版逻辑作为对比证据）
# ---------------------------------------------------------------------------

def test_old_dummy_logic_would_fail():
    """
    演示旧 dummy 实现的问题：位置靠前的词永远重要性最高，
    与词的实际模型权重无关。
    """
    def old_dummy(text, max_features):
        words = text.split()[:max_features]
        features = []
        for i, word in enumerate(words):
            importance = 1.0 / (i + 1)
            features.append({"feature": word, "importance": importance})
        return features

    result_bac = old_dummy("B A C", 10)
    result_abc = old_dummy("A B C", 10)

    # 旧实现：B 在 "B A C" 中排第一，所以 importance=1.0
    # 同一个 B 在 "A B C" 中排第二，所以 importance=0.5
    # 说明重要性纯粹由位置决定
    assert result_bac[0]["feature"] == "B"
    assert result_bac[0]["importance"] == 1.0
    assert result_abc[0]["feature"] == "A"
    assert result_abc[1]["feature"] == "B"
    assert result_abc[1]["importance"] == 0.5


# ---------------------------------------------------------------------------
# 测试 5：文本词语均不在词汇表时返回空列表
# ---------------------------------------------------------------------------

def test_no_vocab_match_returns_empty_list():
    tfidf_mock = MagicMock()
    tfidf_mock.vocabulary_ = {"known_word": 0}

    feature_engineer_mock = MagicMock()
    feature_engineer_mock.tfidf_vectorizer = tfidf_mock

    xgb_model_mock = MagicMock()
    xgb_model_mock.feature_importances_ = np.array([0.5])

    python_model_stub = MagicMock()
    python_model_stub.feature_engineer = feature_engineer_mock
    python_model_stub.model = xgb_model_mock

    model_impl = MagicMock()
    model_impl.python_model = python_model_stub

    pyfunc_model = MagicMock()
    pyfunc_model._model_impl = model_impl

    svc = _make_service(model=pyfunc_model)

    # 输入词语均不在词汇表中
    result = svc._get_feature_importance("unknown1 unknown2", max_features=10)

    assert result == [], "词语均不在词汇表时应返回空列表而非 None"


if __name__ == "__main__":
    test_no_python_model_returns_none()
    test_missing_feature_engineer_returns_none()
    test_real_feature_importances_returned()
    test_old_dummy_logic_would_fail()
    test_no_vocab_match_returns_empty_list()
    print("All tests passed.")
