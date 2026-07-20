# system_mgmt NATS: 按 (username, sync_source_id) 查询用户组织树

- 日期:2026-07-14
- 模块:server/apps/system_mgmt
- 适用版本:master(`97218a227b` 之后)

## 1. 背景与目标

内部服务(如 stargazer、cmdb、opspilot 等 agent)需要按 (username, sync_source_id) 唯一定位一个外部同步用户,并拿到其「有权限的组织」树状结构,供下游做权限范围计算、资源路由或展示。

现状:
- `server/apps/system_mgmt/nats/users.py` 中 `get_authorized_groups_scoped(actor_context, include_children)` 依赖调用方 token + current_team,服务间调用拿不到 actor_context。
- `get_all_groups()` 返回**全量**组织树(全租户所有组织),不能按用户过滤。
- `GroupUtils.build_group_tree(queryset, is_superuser, user_groups)` 工具已存在,可复用。
- `core/views/index_view.py::login_info` 已经以同形态(`group_tree` 字段)返回给前端,本设计与其保持一致。

目标:新增 1 个 NATS handler,签名简单、无 caller 鉴权,行为与 `login_info` 的 `group_tree` 字段一致。

## 2. 不在范围内

- 不做 caller 鉴权(明确为内部服务间调用,信任调用方)。
- 不引入缓存(明确为低频调用,准确优先;后续若高频可在该函数上挂 `cache.get_or_set`,不影响契约)。
- 不改 `User`、`Group`、`UserSyncSource` 模型,不改 `GroupUtils`。
- 不改前端、不发新版本协议;本接口仅服务 Python 内部 RPC。
- 不处理 `sync_source_id` 不存在的边界(数据库 FK 约束会在 `filter` 时返回 0 命中,落入"user not found"路径)。
- 不支持批量 (username, sync_source_id) 查询。

## 3. 契约

### 3.1 主题与函数

- NATS 主题:`system_mgmt.get_user_group_tree`(函数名即主题名,与 `get_all_groups`/`search_users`/`get_group_users_scoped` 一致)。
- 位置:`server/apps/system_mgmt/nats/users.py`,在 `get_all_groups` 之后追加。
- 装饰:`@nats_client.register`,与同文件其它 handler 同风格。

### 3.2 入参(位置参数)

| 顺序 | 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|------|
| 0 | `username` | str | 是 | 用户名;空串视为缺失 |
| 1 | `sync_source_id` | int / None / "" | 否(默认 None) | `UserSyncSource.id`;**`None` 或空串都表示本地用户(`User.sync_source IS NULL`)**;其余尝试 `int(...)` 强转,字符串数字合法,强转失败返回 `invalid sync_source_id` |

调用方语义:
- 本地用户(不接第三方同步源)→ `sync_source_id=None` 或 `""`(或不传,默认 None)
- 同步源用户(AD/LDAP/Feishu/WeChat 等)→ `sync_source_id=<UserSyncSource.id>`
- 字符串数字会被强转;非数字且非空且非 None 视为入参错误

### 3.3 出参

正常:

```json
{
  "result": true,
  "data": {
    "user_id": 12,
    "username": "alice",
    "domain": "domain.com",
    "group_list": [3, 5, 9],
    "group_tree": [
      {
        "id": 1,
        "name": "Default",
        "subGroupCount": 1,
        "subGroups": [
          {
            "id": 3,
            "name": "Ops",
            "subGroupCount": 0,
            "subGroups": [],
            "hasAuth": true,
            "role_ids": [1, 2],
            "is_virtual": false
          }
        ],
        "hasAuth": false,
        "role_ids": [],
        "is_virtual": false
      }
    ]
  }
}
```

`group_tree` 每个节点字段固定为 `id` / `name` / `subGroupCount` / `subGroups` / `hasAuth` / `role_ids` / `is_virtual`(若该节点有 `parent_id` 则附带 `parentId`)。这与 `GroupUtils.build_group_tree` 在 `is_superuser=False` 时的当前输出完全一致,不做字段裁剪或扩展。

错误:

| 场景 | result | message |
|------|--------|---------|
| `username` 缺失/空串 | `false` | `"username is required"` |
| `sync_source_id` 非 None/"" 且强转失败 | `false` | `"invalid sync_source_id"` |
| 用户不存在(count == 0) | `false` | `"user not found"` |
| 用户不唯一(count > 1) | `false` | `"expected 1 user, got {n}"` |
| 数据库/未知异常 | `false` | `"internal error: {e}"`,并 `logger.exception(e)` |

不设置 `error_code` 字段(本接口无 token 失效等错误码语义;保持与 `get_all_groups` 一致,仅 message 区分)。

## 4. 数据流

```
NATS 请求  {username, sync_source_id}
   │
   ▼
[1] 参数校验
    - username 空/None → "username is required"
    - sync_source_id 为 None 或空串("") → 归一化为 None,表示本地用户,跳过强转
    - sync_source_id 其它情况尝试 int(...),强转失败 → "invalid sync_source_id"
   │
   ▼
[2] User 查询(分支)
    - sync_source_id is None → User.objects.filter(username=u, sync_source__isnull=True)
    - 否则               → User.objects.filter(username=u, sync_source_id=src)
    .count()  (一次 count 查询)
   ├─ 0 → "user not found"
   ├─ >1 → "expected 1 user, got N"
   └─ 1 → user = qs.first()
   │
   ▼
[3] 组树构建(完全复用 verify_token 的"非超管"路径)
    visible_ids = _collect_ancestor_group_ids(user.group_list)
    queryset   = list(Group.objects
                       .prefetch_related("roles")
                       .filter(id__in=visible_ids)
                       .order_by("id"))
    group_tree = GroupUtils.build_group_tree(
                     queryset,
                     is_superuser=False,
                     user_groups=[int(g) for g in user.group_list])
   │
   ▼
[4] 返回 {result: True, data: {user_id, username, domain, group_list, group_tree}}
```

关键决策:
- **不查 is_superuser**:`verify_token` 用 `is_superuser` 决定"全量"还是"局部",取决于角色判断(`Role.objects.filter(id__in=all_role_ids)`)。本接口仅按 group_list 拿用户的"个人组织树",不接管其角色判断(目标用户的角色是否蕴含 admin 是上游的语义)。语义上是「目标用户**作为普通用户视角**看到自己组织树的形态」,所以直接走 `is_superuser=False` 路径。
- **不做祖先过滤断言**:`_collect_ancestor_group_ids` 已经做了 BFS,不会循环引用。
- **同步强转 int**:`user.group_list` 是 JSONField,可能含 `int` 或 `str`(历史脏数据兼容);统一在传入 `build_group_tree` 前 `int(...)`。`build_group_tree` 内部用 `group.id in user_groups` 判等,强转一致即可。

## 5. 代码放置与依赖

### 5.1 后端 NATS handler(实现)

新增代码块(示意,非最终代码):

```python
# server/apps/system_mgmt/nats/users.py,追加在文件末尾

from .common import _collect_ancestor_group_ids  # 如未导入则补;与 auth.py 同方式


@nats_client.register
def get_user_group_tree(username, sync_source_id=None):
    """按 (username, sync_source_id) 唯一定位用户,返回其组织树(参照 login_info.group_tree 形态)。

    :param username: 用户名
    :param sync_source_id: UserSyncSource 主键;None 或空串表示本地用户(User.sync_source IS NULL);
                         字符串数字会尝试 int() 强转
    :return: 标准 NATS 三段式,data 包含 user_id/username/domain/group_list/group_tree
    """
    if not username:
        return {"result": False, "message": "username is required"}

    # 归一化 sync_source_id:None 或空串走本地用户;其余尝试 int() 强转
    if sync_source_id in (None, ""):
        sync_source_id = None
    else:
        try:
            sync_source_id = int(sync_source_id)
        except (TypeError, ValueError):
            return {"result": False, "message": "invalid sync_source_id"}

    try:
        qs = User.objects.filter(username=username)
        if sync_source_id is None:
            qs = qs.filter(sync_source__isnull=True)
        else:
            qs = qs.filter(sync_source_id=sync_source_id)
        count = qs.count()
        if count == 0:
            return {"result": False, "message": "user not found"}
        if count > 1:
            return {"result": False, "message": f"expected 1 user, got {count}"}
        user = qs.first()

        user_group_ids = [int(g) for g in (user.group_list or [])]
        visible_ids = _collect_ancestor_group_ids(user_group_ids)
        queryset = list(
            Group.objects.prefetch_related("roles")
            .filter(id__in=visible_ids)
            .order_by("id")
        )
        group_tree = GroupUtils.build_group_tree(
            queryset, is_superuser=False, user_groups=user_group_ids
        )
        return {
            "result": True,
            "data": {
                "user_id": user.id,
                "username": user.username,
                "domain": user.domain,
                "group_list": user_group_ids,
                "group_tree": group_tree,
            },
        }
    except Exception as e:
        logger.exception(e)
        return {"result": False, "message": f"internal error: {e}"}
```

- `User`、`Group`、`GroupUtils` 已通过 `from .common import *`(`nats/users.py:1-2`)可见,无需新增 import。
- `_collect_ancestor_group_ids` 来自 `nats/common.py:67`,在 `auth.py:3` 已有 `from .common import _collect_ancestor_group_ids, _verify_token` 的写法,本文件照搬 `from .common import _collect_ancestor_group_ids`。
- `logger` 由 `from .common import *` 透传(同文件其它 handler 使用一致)。

### 5.2 RPC 客户端入口(调用面)

按仓库约定,NATS handler 的所有外部调用统一经过 `server/apps/rpc/system_mgmt.py` 的 `SystemMgmt` 类(`AppClient("apps.system_mgmt.nats_api")`)。因此必须**同步新增 RPC 入口方法**,否则其它服务无法消费本接口。

在 `SystemMgmt` 类中按字母序在 `get_authorized_groups_scoped` 与 `get_client` 之间插入(维持现有排列风格):

```python
def get_user_group_tree(self, username, sync_source_id=None):
    """
    按 (username, sync_source_id) 唯一定位用户,返回其组织树。
    返回结构与 login_info.group_tree 形态一致。

    :param username: 用户名
    :param sync_source_id: UserSyncSource 主键(int);None 或空串表示本地用户(User.sync_source IS NULL)
    :return: {"result": bool, "data": {"user_id", "username", "domain", "group_list", "group_tree"} | "message": str}
    """
    return_data = self.client.run("get_user_group_tree", username=username, sync_source_id=sync_source_id)
    return return_data
```

要点:
- 参数命名与位置参数(传给 `AppClient.run`)完全对齐 NATT 主题,保持 `self.client.run("get_user_group_tree", username=..., sync_source_id=...)` 形式 —— 与同文件 `get_authorized_groups_scoped` 等使用 `kwargs` 透传的写法一致,便于 NATS client 按关键字路由。
- 调用方在其它服务写 `from apps.rpc.system_mgmt import SystemMgmt; SystemMgmt().get_user_group_tree("alice", 1)` 即可。
- 不引入新 RPC 类,沿用 `SystemMgmt` 单一入口。

## 6. 测试计划

`server/apps/system_mgmt/tests/` 下新增 `test_nats_get_user_group_tree.py`,使用 `APITestCase` / `TransactionTestCase`(参考 `test_nats_api_test.py`)。

| # | 用例 | 期望 |
|---|------|------|
| 1 | 正常:单一命中,`group_list` 含 1 个组,该组父级也在树中 | `result=True`;`group_tree` 非空;叶子 `hasAuth=True`、父级 `hasAuth=False`;`group_list` 全部为 int |
| 2 | 正常:`group_list=[]` | `result=True`;`group_tree=[]`;`group_list=[]` |
| 3 | 用户不存在 | `result=False, message="user not found"` |
| 4 | 多个用户匹配(同 username+sync_source_id 故意建两条) | `result=False, message` 含 `got 2` |
| 5 | 缺 `username`(传空串/None) | `result=False, message="username is required"` |
| 6 | `sync_source_id` 传 `"abc"` | `result=False, message="invalid sync_source_id"` |
| 7 | `sync_source_id` 传 `"3"`(字符串数字) | `result=True`,正常返回 |
| 8 | `group_list` 含 str 数字(模拟 JSONField 脏数据) | 强转后正常,树中能找到该组 |
| 9 | 调用方构造数据库异常(如 monkeypatch `Group.objects.filter` 抛错) | `result=False, message` 含 `internal error`,`logger.exception` 被调用 |
| 10 | `group_tree` 节点字段白名单(防止后续 `GroupUtils` 改动扩散) | 每个节点只含 `id/name/subGroupCount/subGroups/hasAuth/role_ids/is_virtual` ± `parentId` |
| 11 | RPC 入口 `SystemMgmt.get_user_group_tree` | monkeypatch `apps.rpc.system_mgmt.AppClient.run`(或 `system_mgmt.SystemMgmt.client.run`),断言以 `"get_user_group_tree"` 为名、`username`/`sync_source_id` 关键字正确透传;handler 返回 `{"result": True, "data": {...}}` 时 RPC 原样返回 |

测试覆盖率目标:行覆盖 ≥ 75%(本函数 1 个新文件,函数体 + 4 个早返回路径 + 异常路径全部覆盖,自然达成)。

## 7. 风险与回滚

- **风险 1:count 查询多余一次**。`count() + first()` 两次查询,代价为 1 次 `SELECT COUNT(*)`;可用 `qs.first()` + `len(qs)` 替代,语义略变(2 行时不再报错而是返回第一条)。选择 `count` 因为**用户明确"严格唯一+多个报错"**。
  - 回滚:替换为 `getattr(qs, "__len__")` 或 `len(qs)` 不影响契约。
- **风险 2:`_collect_ancestor_group_ids` 全表 values_list**。当组织表很大时单次全量;与 `verify_token` 一致,接受现状(已有性能预算)。
- **风险 3:`is_superuser=False` 不代表真实权限**。若调用方期望"目标用户真实可看的组织"取决于其 admin 角色,需改用 `verify_token` 内的 `Role` 判断逻辑再分支。**当前契约明确以"用户个人组织"为口径,角色判断交由调用方**。
- **回滚**:涉及 `server/apps/system_mgmt/nats/users.py`(NATS handler)与 `server/apps/rpc/system_mgmt.py`(RPC 入口)两个文件新增方法,无 schema/依赖变更,直接 `git revert` 单 commit 即可。

## 8. 后续可选(不做)

- 高频场景:在函数顶部加 `cache.get_or_set(f"user_group_tree:{sync_source_id}:{username}", ..., 60)`;同时让 `User.save` 中已有的 `clear_user_permission_cache` 增加对该 key 的失效(在 `apps/core/utils/permission_cache.py` 扩展)。本次不做。
- `sync_source_id` 缺省为 `None` 时降级到"只按 username 查唯一"——本次不做,避免歧义。
