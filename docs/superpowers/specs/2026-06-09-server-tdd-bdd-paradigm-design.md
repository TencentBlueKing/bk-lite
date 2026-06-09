# Server TDD/BDD 开发范式整改 — 设计 spec

- 日期：2026-06-09
- 范围：`server/`（Django 后端）测试体系
- 交付物语言：中文；规范文档落点：`server/docs/testing-guide.md`

## 背景与问题

整改前 `server` 测试体系存在以下问题：

1. **BDD 跑不起来**：仓库有 20 个 `.feature` 文件与配套步骤定义，但 `pytest-bdd` 既不在
   `pyproject.toml` 也不在虚拟环境中；`factory_boy`（`apps/base` 测试依赖）同样缺失。
2. **`pytest.ini` 配置错误**：
   - `addopts` 写死 `./apps/core/tests` 与 `--cov=apps/core`，默认只跑 / 只统计 `core`；
   - 代码用 `@pytest.mark.bdd/unit/...` 但 marker 未注册；
   - 文件尾部混入 `[tool.pytest.ini_options]`（pyproject 语法，`.ini` 中无效）。
3. **BDD 目录三种风格并存**：
   - `apps/alerts/test/bdd/`（单数 `test`）
   - `apps/base/tests/bdd/{features,step_defs}/` + `@scenario` 装饰器
   - `apps/cmdb|operation_analysis/tests/bdd/`（扁平 + `scenarios(FEATURE)`）

## 决策

- 交付范围：**全面整改**（规范文档 + 基建修复 + 迁移存量测试）。
- BDD 统一约定：**扁平式 `scenarios(FEATURE)`**（cmdb / operation_analysis 风格）。
- 文档语言：中文；落点 `server/docs/testing-guide.md`。

## 目标结构

```
apps/<app>/tests/
  conftest.py / factories.py
  test_<x>_pure.py      # 纯单元，无 DB/IO
  test_<x>_service.py   # service 层，mock 外部依赖
  test_<x>_views.py     # DRF 接口层，api_client
  bdd/
    <feature>.feature   # 中文 Gherkin
    test_<feature>_bdd.py  # scenarios(FEATURE)
    conftest.py
```

测试分层（金字塔）：`_pure` → `_service` → `_views`，能上浮就不下沉。

## 实施内容

1. **依赖**：`pytest-bdd`（8.1.0）、`factory-boy`（3.3.3）加入 `dev` 组。
2. **`pytest.ini`**：
   - 删除写死的 `./apps/core/tests` 路径与重复 `[tool.pytest.ini_options]` 段；
   - `testpaths = apps`、`--cov=apps`；
   - 注册 marker：`unit / integration / bdd / slow`。
3. **目录迁移**：
   - `apps/alerts/test/` → `apps/alerts/tests/`（feature 用 `Path(__file__).parent` 加载，迁移安全）；
   - `apps/base/tests/bdd/{features,step_defs}/` 拍平为 `apps/base/tests/bdd/`，
     步骤文件由 5 个 `@scenario` 改为单个 `scenarios(FEATURE)`，conftest 上移。
4. **文档**：新增 `server/docs/testing-guide.md`；更新根 `CLAUDE.md` 的 Testing 段落指向新规范。

## 验证

- `pytest --markers`：四个 marker 已注册。
- cmdb BDD（FakeGraphClient，不依赖 DB）：通过；base BDD 5 个场景按新结构正确收集并绑定。
- 需要 DB 的用例在无 PostgreSQL 的沙箱中报连接错误，属环境限制，非本次改动引入。

## 范围外

- 不修复用例本身的业务断言；不补齐覆盖率到指定阈值；
- 其余 app 未来新增/改动测试时按本规范逐步迁移，不在本次一次性重写。
