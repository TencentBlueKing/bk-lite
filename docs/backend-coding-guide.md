# 后端编码规范 / 高频陷阱清单

> 后端开发的预防性规范:写代码时照此避坑。每条给 **✅ 正确姿势** 与 **❌ 反模式**。
> 与 [QUALITY_SCORE](../QUALITY_SCORE.md)(判定)、`server/docs/testing-guide.md`(测试)、[SECURITY](../SECURITY.md) / [RELIABILITY](../RELIABILITY.md)(安全/可靠)配套。
> 用法:改 `server/` 或 `agents/` 代码前,对照与你改动相关的小节。

## 1. 鉴权与多租户(最高频 —— 务必先看)

- ✅ **每个 DRF view/action 显式权限校验**,`@HasPermission(...)` 绝不注释掉;mixin 默认权限要确认覆盖到每个 action。
  - ❌ 权限装饰器被注释/缺失,任意已登录用户即可执行敏感操作或枚举全量。
- ✅ **每个 NATS handler 校验调用方与 org**,不信任消息体里的 `group_id`/`pusher`/身份字段。
  - ❌ 信任客户端传入的身份字段 → 内网任意节点跨组织读写。
- ✅ **`skip_permission` 不得硬编码旁路**;采集/内部调用也要带真实 caller。
- ✅ **权限过滤 fail-closed**:权限数据为空 → 返回 `none()`,绝不 fail-open 返回全量。
- ✅ **`@api_exempt` 仅限真正公开端点**;任何写操作禁用。
- ✅ **按对象读取校验归属(防 IDOR)**:`get_object` 限定在调用者租户/团队内。
- ✅ **跨团队操作校验 team 归属**:重跑/批量操作前确认对象属于调用者。

## 2. 查询与性能

- ✅ **列表/批量接口强制分页上界**,拒绝 `page_size=-1` 或无界拉取。
  - ❌ 无上界查询/循环 → 可被远程触发 OOM/DoS。
- ✅ **不把整表加载进内存做过滤/唯一性/统计**,用 DB 层 `filter`/`exists`/`annotate`/`count`。
- ✅ **FK/M2M 用 `select_related`/`prefetch_related` 防 N+1**。
- ✅ **多次 `count()`/独立查询合并为单次 `annotate`**;热路径禁冗余 `count()`/`exists()` 调试查询。
- ✅ **高频过滤字段加 `db_index`**;重查询结果加缓存(带失效)。

## 3. 事务与一致性

- ✅ **多表/多步写包 `transaction.atomic()`**,部分失败整体回滚。
- ✅ **通知/外部副作用放 `transaction.on_commit`**,不在落库成功前推送。
  - ❌ 先发通知后落库 → 失败时通知与数据不一致。
- ✅ **read-modify-write 用 `select_for_update` 或 `F()` 原子更新**,防并发竞态。
- ✅ **进程级缓存必须有失效机制**,配置变更后能刷新。

## 4. 输入边界与错误响应

- ✅ **不裸 `int(request.GET.get(...))` / 不裸字典取键**,用 serializer 校验,或 `try` + 返回 **400**。
  - ❌ 裸转换/裸取键 → 非法输入触发 500,或崩溃 worker。
- ✅ **鉴权/授权失败返回 403**,不是 500;错误响应结构统一。
- ✅ **不吞异常**:`except` 要么处理要么上抛 + 记日志;禁空/裸 `except` 返回脏数据。
- ✅ **NATS handler 入参做类型/存在校验**,非法输入不得崩 worker。

## 5. 序列化与契约

- ✅ **禁止 `fields = "__all__"`**,显式列字段,新增字段不会意外外泄。
- ✅ **敏感字段(secret/password/token)`write_only=True`**,绝不随 GET 响应返回。
- ✅ **JSONField 入库前做结构校验**,不静默存任意值。

## 6. 密钥与下发(交叉,详见 SECURITY / RELIABILITY)

- ✅ **密钥不明文返回 / 不进日志**;解密失败跳过或告警,绝不回退返回密文。
- ✅ **下发链路校验 TLS / host key**,禁 `skip-tls` / `AutoAddPolicy` / `StrictHostKeyChecking=no`。
- ✅ **下发不伤宿主**:资源边界、幂等可回滚、不可逆操作预检 —— 见 [RELIABILITY §2.5](../RELIABILITY.md)。

## 7. 数据库可移植与图库

- ✅ **禁原生 SQL**:走 Django ORM(`DB_ENGINE` 多方言,raw SQL 跨库易碎);确需复杂查询用 ORM 表达式。
- ✅ **图库(CMDB)用参数化查询**,禁拼接 Cypher / 禁 Neo4j 语法(本项目用 FalkorDB)。

## 8. 架构卫生

- ✅ **控制文件/类规模**:发现 God 文件(>500 LOC)/God 类及时拆分;重复逻辑(3+ 处)抽公共 helper,避免漂移漏改。

---

## 提交前快速自检(后端)

改 `server/` / `agents/` 时逐条对照:
- [ ] view/handler 有显式鉴权,fail-closed,不信任客户端身份字段
- [ ] 列表有分页上界,无全量内存过滤,FK 有 select_related/prefetch
- [ ] 多步写有 `atomic`,通知在 `on_commit`,RMW 原子
- [ ] 输入经校验,异常不吞,失败码语义正确(400/403 非 500)
- [ ] serializer 无 `__all__`,敏感字段 write_only
- [ ] 无原生 SQL,图查询参数化
- [ ] 新增行为有测试,覆盖率达标(见 [QUALITY_SCORE §4](../QUALITY_SCORE.md))
