import pydantic.root_model  # noqa
"""core 小工具模块剩余未覆盖分支的真实行为测试。

- loader.LanguageLoader._load_language_file:
    * 主语言文件读取/解析抛异常 -> 容错为空 (61-62)
    * enterprise 语言文件读取/解析抛异常 -> 容错保留主文件结果 (72-73)
- open_base.OpenAPIViewSet.as_view: super().as_view 抛异常 -> 记日志并 re-raise (62-64)
- time_util.get_crontab_next_runs:
    * base_time=None 时默认使用 now，仍返回 count 条递增结果 (67)
    * croniter 迭代阶段抛异常 -> 包装成 ValueError (76-77)

策略：真实调用被测函数；仅对真实文件 IO / 第三方迭代器边界打桩以制造异常，
断言被测代码的真实容错返回值或真实抛出的异常类型。
"""
import os

import pytest

pytestmark = pytest.mark.unit


# ============================================================================
# loader._load_language_file —— yaml 读取异常容错
# ============================================================================


class TestLoaderFileReadException:
    def _make(self, tmp_path, app, lang, main_content):
        base = os.path.join(str(tmp_path), "apps", app, "language")
        os.makedirs(base, exist_ok=True)
        with open(os.path.join(base, f"{lang}.yaml"), "w", encoding="utf-8") as f:
            f.write(main_content)

    def test_main_file_yaml_load_raises_returns_empty(self, tmp_path, monkeypatch):
        """主语言文件存在，但 yaml.safe_load 抛异常 -> result 容错为空 dict (61-62)。"""
        from apps.core.utils.loader import LanguageLoader, clear_language_cache

        app = "__main_read_fail__"
        clear_language_cache(app=app)
        self._make(str(tmp_path), app, "en", "os:\n  linux: Linux\n")
        monkeypatch.chdir(tmp_path)

        import apps.core.utils.loader as loader_mod

        monkeypatch.setattr(loader_mod.yaml, "safe_load", lambda *a, **k: (_ for _ in ()).throw(ValueError("bad yaml")))

        loader = LanguageLoader(app=app, default_lang="en")
        # 主文件解析异常被吞，且无 enterprise -> 空翻译
        assert loader.translations == {}
        clear_language_cache(app=app)

    def test_enterprise_file_read_raises_keeps_main(self, tmp_path, monkeypatch):
        """enterprise 文件存在但读取/解析抛异常 -> 保留主文件结果 (72-73)。"""
        from apps.core.utils.loader import LanguageLoader, clear_language_cache

        app = "__ent_read_fail__"
        clear_language_cache(app=app)
        # 主文件
        self._make(str(tmp_path), app, "en", "os:\n  linux: Linux\n")
        # enterprise 文件
        ent_dir = os.path.join(str(tmp_path), "apps", app, "enterprise", "language")
        os.makedirs(ent_dir, exist_ok=True)
        with open(os.path.join(ent_dir, "en.yaml"), "w", encoding="utf-8") as f:
            f.write("os:\n  mac: Mac\n")
        monkeypatch.chdir(tmp_path)

        import apps.core.utils.loader as loader_mod

        real_safe_load = loader_mod.yaml.safe_load
        calls = {"n": 0}

        def flaky_safe_load(stream, *a, **k):
            calls["n"] += 1
            # 第一次（主文件）正常，第二次（enterprise）抛异常
            if calls["n"] == 1:
                return real_safe_load(stream, *a, **k)
            raise ValueError("enterprise bad yaml")

        monkeypatch.setattr(loader_mod.yaml, "safe_load", flaky_safe_load)

        loader = LanguageLoader(app=app, default_lang="en")
        # 主文件内容保留，enterprise 解析失败被吞
        assert loader.get("os.linux") == "Linux"
        assert loader.get("os.mac", "fallback") == "fallback"
        clear_language_cache(app=app)


# ============================================================================
# open_base.OpenAPIViewSet.as_view —— 构建失败 re-raise
# ============================================================================


class TestOpenAPIViewSetAsViewError:
    def test_as_view_super_raises_is_logged_and_reraised(self):
        # 被测代码用 super(ViewSet, cls).as_view -> MRO 中 ViewSet 之后是 ViewSetMixin
        from rest_framework.viewsets import ViewSetMixin

        from apps.core.utils.open_base import OpenAPIViewSet

        class MyOpen(OpenAPIViewSet):
            pass

        # 让上游 as_view 抛异常 -> 进入 except 分支 -> 记日志并向上抛
        import unittest.mock as mock

        with mock.patch.object(ViewSetMixin, "as_view", side_effect=RuntimeError("build boom")):
            with pytest.raises(RuntimeError, match="build boom"):
                MyOpen.as_view(actions={"get": "list"})


# ============================================================================
# time_util.get_crontab_next_runs —— 默认 base_time / 迭代异常
# ============================================================================


class TestCrontabDefaultsAndIterError:
    def test_default_base_time_uses_now(self):
        """不传 base_time -> 默认 now，仍应返回 count 条且严格递增的合法时间串。"""
        from apps.core.utils.time_util import get_crontab_next_runs

        runs = get_crontab_next_runs("* * * * *", count=3)
        assert len(runs) == 3
        assert runs == sorted(runs)
        # 每条都能被解析回 datetime（格式正确）
        from datetime import datetime

        for r in runs:
            datetime.strptime(r, "%Y-%m-%d %H:%M:%S")

    def test_iteration_error_wrapped_as_valueerror(self, monkeypatch):
        """is_valid 通过但 croniter 迭代阶段抛异常 -> 被包装成 ValueError (76-77)。"""
        import apps.core.utils.time_util as tu

        class BoomCron:
            # 被测代码先调用 croniter.is_valid(expr) -> True，再构造实例迭代
            @staticmethod
            def is_valid(expr):
                return True

            def __init__(self, *a, **k):
                pass

            def get_next(self, *a, **k):
                raise RuntimeError("iter boom")

        # 整体替换模块内引用的 croniter，使 is_valid 通过但 get_next 抛错
        monkeypatch.setattr(tu, "croniter", BoomCron)

        with pytest.raises(ValueError, match="Failed to calculate next runs"):
            tu.get_crontab_next_runs("* * * * *")
