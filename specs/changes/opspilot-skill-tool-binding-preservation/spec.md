# 智能体工具绑定的保存与故障定位

智能体的工具绑定保存在 `LLMSkill.tools`。工具目录受版本、当前组织和工具查看权限影响。目录为设置页提供展示信息及可添加的选项，智能体详情提供已保存的绑定。

## 已复现的行为

- 设置页原先在目录加载完成后用匹配结果覆盖绑定。已保存的工具全部不在本次目录时，页面显示为空，随后保存提示词也可能写入空数组。
- 只调整组织也能触发上述写入。以仅绑定 Kubernetes 的智能体为例，当前工具目录仅返回 SSH；在旧版详情设置页追加管理组织和使用组织并保存，请求同时发送 `tools: []`。若另有可见的已绑定工具，请求只保留匹配部分。列表卡片的「编辑」弹窗仅提交已注册的表单字段，不携带工具。两个入口都只更新选中的智能体。
- 后端原先整行保存智能体。两个编辑请求交错时，未携带工具字段的旧请求也可能覆盖较新请求的工具配置。
- 本地证据来自当前共享代码及数据库回归。客户商业版的镜像版本、更新路径和事发时数据未知。

## 修复后的行为

- 按保存的绑定展示工具；目录中无法匹配的项保留原名称和配置并标注。内置工具支持按稳定名称识别，外部 MCP 按绑定身份匹配。勾选其他工具保留不可见项，仍可逐项主动移除。
- 未编辑工具时，页面保存请求省略 `tools`。主动移除最后一项提交 `tools: []`。后端只写本次更新涉及的字段。详情加载失败不能提交空白表单。
- 此修复无需数据迁移。部署后对仍存在的绑定生效。数据库里已经为空的实例需要依据历史副本恢复。

## 现场只读定位

先保留当前数据库快照，暂停在受影响的设置页保存。在后端 Django shell 内执行下列查询，只输出实例 ID 和绑定数量。可以在升级前备份的独立副本上执行相同查询，比较同一实例。

```python
from apps.opspilot.models import LLMSkill

skills = LLMSkill.objects.filter(is_template=False).order_by("pk")
for pk, tools in skills.values_list("pk", "tools").iterator(chunk_size=100):
    print(pk, len(tools) if isinstance(tools, list) else "格式异常")
```

- 实例仍有绑定且页面为空时，在同一组织、同一账号下对照智能体详情与工具目录的名称及 ID。目录中缺项还会影响工具可用性，应核对该版本是否安装、同步了相应工具，以及当前组织的可见权限。
- 确认实例从非空变为空时，优先在独立副本核对升级前备份或时间点恢复数据，确认组织、实例标识和环境内工具 ID 的映射。恢复范围限定到受影响实例的工具字段，保留升级后其他业务数据。完整连接参数可能含凭据，运维核对在受控环境进行。
- 操作日志中的智能体编辑时间可以辅助定位写入时机。调用历史可帮助辨认使用过的工具，无法证明完整绑定清单与配置。
- 核对组织调整事件时，以该次保存为前后分界。若有网关请求记录，只需核对方法、路径、目标实例、是否出现 `tools` 及其数量。详情设置页使用 PUT，列表编辑弹窗使用 PATCH。普通「编辑智能体」日志没有字段差异。单个实例的保存无法解释其他未编辑实例也被清空，后者应另查实际绑定及当前组织的目录可见性。

### 多个智能体同时看不到 Kubernetes 工具

旧版设置页在打开时用当前账号可见的工具目录构造已选列表。回归用例保留智能体上的 SSH 和 Kubernetes 绑定，只让目录返回 SSH。旧版仅显示 SSH；修复后两项均显示，缺项标注「当前目录不可见」。普通 Kubernetes 工具和 Kubernetes 数据采集工具各自覆盖这个场景，全程无需保存。

可在客户后端已有的 Django shell 中执行以下只读检查，无需事先知道智能体 ID。输出只包含目录 ID、组织 ID、智能体 ID、绑定位置与匹配状态。不要导出完整的 `tools`、`params` 或 kubeconfig。

```python
from apps.opspilot.models import LLMSkill, SkillTools

variants = {"kubernetes", "kubernetes_data_collection"}
catalog = dict(SkillTools.objects.filter(is_build_in=True, name__in=variants).values_list("pk", "name"))
print("K8s 目录 (ID, 工具名, 组织)", list(SkillTools.objects.filter(pk__in=catalog).order_by("pk").values_list("pk", "name", "team")))
skills = LLMSkill.objects.all()
if any(f.name == "is_template" for f in LLMSkill._meta.fields):
    skills = skills.filter(is_template=False)
for pk, bindings in skills.order_by("pk").values_list("pk", "tools").iterator(chunk_size=100):
    hits = []
    if not isinstance(bindings, list):
        print(pk, "绑定格式异常")
        continue
    for pos, binding in enumerate(bindings):
        if not isinstance(binding, dict):
            continue
        name = binding.get("rawName") or binding.get("name")
        name = name if isinstance(name, str) and name in variants else None
        tool_id = binding.get("id")
        catalog_name = catalog.get(tool_id) if isinstance(tool_id, int) else None
        keys = {p.get("key") for p in (binding.get("kwargs") or []) if isinstance(p, dict) and isinstance(p.get("key"), str)}
        if name or catalog_name or keys.intersection({"kubernetes_instances", "kubeconfig_data"}):
            state = "名称与 ID 匹配" if catalog_name and catalog_name == name else "需核对旧 ID、名称或参数特征"
            hits.append((pos, tool_id if isinstance(tool_id, int) else None, name, state))
    print(pk, "全部绑定数", len(bindings), "K8s 线索", hits)
```

目录表有记录时，再用受影响账号和组织查看设置页实际收到的 `skill_tools/` 响应，只核对名称和 ID。数据库目录和账号可见目录可能不同。实例绑定仍在、目录 ID 失配时也应核对实际调用：当前运行时按正整数 ID 加载这两套工具。排查目录归属与 ID 映射期间，保留原绑定及其集群配置。

若现场输出没有 K8s 线索，在升级前备份副本上执行相同查询，按同一实例与绑定位置核对。旧绑定只有已失效的 ID、没有名称或可识别参数时，仅凭当前库无法判定其原类型。两份副本确认绑定丢失后，仅从该实例自己的历史配置恢复受影响项。
