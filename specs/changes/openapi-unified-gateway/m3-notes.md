# M3 实现备忘

文档聚合与治理门禁实现期决策。

## 实现细节决策

1. **双租户门禁做成 governance 测试而非 CI 配置**：`tests/tenant_coverage.py`
   为显式覆盖登记表（端点 path → 双租户测试引用列表），`test_governance.py`
   校验：注册表每个端点必有登记、每条引用可解析、登记项无陈旧残留，并含
   门禁自验证用例（未登记端点必被检出）。门禁随 pytest 自动生效，
   **不依赖任何 CI 平台配置**——新暴露端点未登记测试即红，合并被拒。
2. **`_docs` 为最小可行版本**：内部端点从装饰器注册表内省 DRF serializer
   （字段类型 / required / default / choices / min·max），外部服务列
   `doc_url` 链接；不追求完整 OpenAPI 3.0 规范。响应结构上线即冻结
   （additive-only），身份字段（注入键）天然不出现在对外 schema 中并有
   测试锁定。需认证访问（与 `_me` 同水位）。
3. **审计日志补齐 `team` 字段**：至此审计字段与 design.md 5.3 对齐
   （user / domain / credential / team / method / path / status /
   duration_ms / size）。
4. **CODEOWNERS 以注释模板落仓**：仓库原无 `.github/CODEOWNERS`；规则
   （网关核心包、各 app `openapi_serializers.py`、change 目录）已写入但
   注释保留，**须团队确认 owner handle 后取消注释启用**——错误的 owner
   比没有更糟（静默无人评审）。
5. **命名评审流程落地为开发者指南**：`apps/core/openapi/README.md` 含
   暴露四步操作指引、inject 选型表、运行期 env 清单与评审 checklist，
   作为 `@openapi_expose` 变更评审的执行依据。

## 测试

`apps/core/openapi/tests` 共 72 项全部通过（M3 新增 8 项：governance 门禁
5 项 + `_docs` 3 项）。

## M3 遗留到 M4 / 团队动作

- CODEOWNERS owner handle 确认后取消注释；
- CI 平台若需单独的门禁 job（而非随全量 pytest），由 CI 维护者按
  `pytest apps/core/openapi/tests/test_governance.py` 配置。
