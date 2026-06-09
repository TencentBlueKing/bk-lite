## Why

OpsPilot 已有 Redis、MySQL、Oracle 三种内置数据库工具，均支持多实例配置。MSSQL 工具的后端 LLM 工具函数（30+ tools）已在 `server/apps/opspilot/metis/llm/tools/mssql/` 完成，但仍停留在单实例扁平参数模式（host/port/database/user/password），且未注册为内置工具、没有前端编辑器。需要将其升级为多实例协议并补齐注册与 UI，使 MSSQL 与其他数据库工具具备一致的配置和运行体验。

## What Changes

- 将 MSSQL 工具的 `CONSTRUCTOR_PARAMS` 从单实例扁平字段升级为 `mssql_instances` + `mssql_default_instance_id` 多实例协议
- 新增 `mssql/connection.py`，实现多实例解析、实例解析、测试连接、LLM 提示生成
- 在 `builtin_tools.py` 中注册 MSSQL 为内置工具（id=-4）
- 在 `chat_service.py` 中添加 MSSQL 内置工具分支
- 在 `llm_view.py` 中添加 `test_mssql_connection` API 端点
- 在 `tools_loader.py` 中为 MSSQL 启用 `enable_extra_prompt=True`
- 新增前端 `mssqlToolEditor.tsx` 多实例编辑器组件
- 在 `toolSelector.tsx` 中集成 MSSQL 工具检测与编辑器路由
- 在 `skill.ts` 中添加 `testMssqlConnection` API 调用
- 添加中英文 i18n 键

## Capabilities

### New Capabilities
- `mssql-tool-multi-instance`: MSSQL 数据库工具多实例配置能力，包括多实例持久化、默认实例与显式切换、批量执行、测试连接、前端编辑器、LLM 上下文注入

### Modified Capabilities
（无需修改现有能力）

## Impact

**后端代码变更:**
- 新增: `server/apps/opspilot/metis/llm/tools/mssql/connection.py`
- 修改: `server/apps/opspilot/metis/llm/tools/mssql/__init__.py`（CONSTRUCTOR_PARAMS 升级）
- 修改: `server/apps/opspilot/services/builtin_tools.py`（注册 id=-4）
- 修改: `server/apps/opspilot/services/chat_service.py`（添加 mssql 分支）
- 修改: `server/apps/opspilot/viewsets/llm_view.py`（添加测试端点）
- 修改: `server/apps/opspilot/metis/llm/tools/tools_loader.py`（enable_extra_prompt）

**前端代码变更:**
- 新增: `web/src/app/opspilot/components/skill/mssqlToolEditor.tsx`
- 修改: `web/src/app/opspilot/components/skill/toolSelector.tsx`
- 修改: `web/src/app/opspilot/api/skill.ts`
- 修改: `web/src/app/opspilot/locales/zh.json`、`en.json`

**依赖:** 无新增（pyodbc 已在 pyproject.toml 中）
