# CMDB 企业版代码分层规范

## 目标

`apps/cmdb/enterprise` 是 CMDB 商业版能力的唯一代码区域。

设计目标如下：

- 社区版负责定义扩展点
- 企业版只实现增量能力
- 删除 `apps/cmdb/enterprise` 后，CMDB 自动回退到社区版行为

这意味着 CMDB 商业版能力必须是**只增不改**。企业版代码不能通过隐式覆盖、同名替换、monkey patch 等方式替换社区版主流程。

## 分层规则

企业版代码按**业务能力域**组织，而不是镜像社区版目录结构。

推荐目录形态：

```text
apps/cmdb/
  model_ops/
    extensions.py
  instance_ops/
    extensions.py
  collect/
    extensions.py

  enterprise/
    model_ops/
      __init__.py
      provider.py
    instance_ops/
      __init__.py
      provider.py
    collect/
      __init__.py
      provider.py
      tree.py
      plugins.py
      node_params.py
```

## 职责划分

### 社区版职责

每个能力域在社区版中维护一个固定扩展门面：

- `apps.cmdb.model_ops.extensions`
- `apps.cmdb.instance_ops.extensions`
- `apps.cmdb.collect.extensions`

扩展门面只负责三件事：

1. 定义本能力域的扩展契约
2. 尝试导入 `apps.cmdb.enterprise.<capability>.provider`
3. 在企业版不存在时返回空实现

社区版业务代码只能依赖本域扩展门面，不能直接导入更深层的 enterprise 模块。

### 企业版职责

每个能力域提供一个 `provider.py` 作为该域唯一入口。

例如：

- `apps.cmdb.enterprise.model_ops.provider`
- `apps.cmdb.enterprise.instance_ops.provider`
- `apps.cmdb.enterprise.collect.provider`

`provider.py` 可以继续调用本域内部的其他模块，但社区版代码不允许直接导入这些内部文件。

## 契约规则

每个能力域都应暴露一个小而明确的契约对象，而不是散落的辅助函数。

例如：

- `ModelEnterpriseExtension`
- `InstanceEnterpriseExtension`
- `CollectEnterpriseExtension`

契约对象可以承载的能力包括：

- 额外动作
- 附加校验规则
- 额外展示区块
- 采集对象树增量
- 插件注册钩子
- NodeParams 扩展

如果企业版不存在，扩展门面必须返回空契约对象，并保证无副作用。

## 导入规则

允许的导入边界：

- 社区版代码只能导入 `apps.cmdb.enterprise.<capability>.provider`
- 企业版内部模块只能在本能力域内相互依赖；如需共享能力，应提炼到 CMDB 公共模块后再复用

禁止的模式：

- 在业务代码里散落 `import_module("apps.cmdb.enterprise.xxx")`
- 跨能力域耦合，例如 `instance_ops` 直接导入 `enterprise.collect`
- 企业版通过 monkey patch 或同名覆盖替换社区版主流程

## 运行时流程

任意商业版能力都按如下链路接入：

1. 社区版业务代码进入某个能力域
2. 该能力域调用自己的 `extensions.py`
3. `extensions.py` 尝试加载 `apps.cmdb.enterprise` 下对应的域 provider
4. provider 存在时，拼接企业版增量能力
5. provider 不存在时，使用空实现继续执行社区版流程

这里的“自动具备商业版能力”，本质上是**按固定能力域入口发现**，而不是全包扫描。

换句话说：

- `apps/cmdb/enterprise` 的存在，表示商业版能力可被发现
- 真正启用发生在某个能力域门面加载到匹配 provider 的时候

## 错误处理

必须区分两类情况：

1. **provider 模块不存在**：属于正常回退，返回空实现
2. **provider 模块存在但不符合契约**：属于实现错误，应通过项目统一日志显式暴露，不能静默忽略

CMDB 可以没有企业版，但不能悄悄接受一个损坏的企业版实现。

## 后续商业需求接入流程

以后所有 CMDB 商业版需求都必须遵循以下顺序：

1. 先判断需求归属哪个能力域：`model_ops`、`instance_ops` 或 `collect`
2. 若现有契约已能承载，则只在 `apps/cmdb/enterprise/<capability>/` 下补实现
3. 若现有契约不足，先在社区版 `apps/cmdb/<capability>/extensions.py` 中新增明确扩展点
4. 再由企业版 provider 实现该扩展点

禁止每来一个需求就临时增加一条新的 enterprise 导入路径。

## 与现有 CMDB 代码的衔接

当前仓库已经存在几条早期企业版接入链路：

- `apps/cmdb/services/collect_object_tree.py` 中的采集对象树叠加
- `apps/cmdb/collection/plugins/loader.py` 中的插件包加载
- `apps/cmdb/node_configs/__init__.py` 中的 NodeParams 自动注册

这些现有路径可以继续存在，但后续都应逐步收敛到本文约定的“能力域门面 + provider”模式。

例如当前已有的 `apps/cmdb/enterprise/tree.py`、`apps/cmdb/enterprise/db/` 等历史实现，可以先保留，由对应能力域的 provider 统一编排，而不要求一次性迁移或重构。
