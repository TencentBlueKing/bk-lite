# 补丁管理 · 功能清单

**文档版本：** V1.0
**发布日期：** 2026-07-27
**适用范围：** BK-Lite 补丁管理模块
**编制依据：** [[patch-management-product.md#产品入口]] 与 `server/apps/patch_mgmt`、`web/src/app/patch-manager` 当前代码

## 一、模块定位

补丁管理负责补丁入库、主机纳管、基线评估、风险识别和治理执行。本清单只列当前版本已实现、可由代码或测试核对的能力。

相关架构：[[patch-management-architecture.md#模块职责]]

## 二、功能清单

### 1. 首页与评估概览

| 功能项 | 功能说明 | 规格 / 约束 | 状态 |
|---|---|---|---|
| 治理指标概览 | 展示纳管、覆盖、合规、风险与异常统计 | 合规率分母仅包含已得出明确评估结果的主机；未配置、待评估、评估失败、未知和不适用不计入 | GA |
| 合规分布 | 展示主机合规状态分布 | 按当前用户数据权限统计 | GA |
| 最近任务 | 展示近期治理任务及其状态 | 支持进入执行记录查看详情 | GA |
| 高频风险 | 展示当前高频风险项 | 基于有效评估结果计算 | GA |
| 全量即时评估 | 对当前可见纳管主机发起评估 | 手工评估不受周期评估开关影响 | GA |

> 证据来源：server/apps/patch_mgmt/services/risk_service.py:299-333，server/apps/patch_mgmt/constants/choices.py:185-216，server/apps/patch_mgmt/views/dashboard.py:70-193　|　同步基线：d2769559　|　【已实现】

对应产品：[[patch-management-product.md#首页]]

相关架构：[[patch-management-architecture.md#接口契约]]

### 2. 补丁源

| 功能项 | 功能说明 | 规格 / 约束 | 状态 |
|---|---|---|---|
| 补丁源维护 | 新增、编辑、删除和启停补丁源 | 自定义源创建时归属当前可信团队，数据按组织（组）范围隔离 | GA |
| 连通性检测 | 使用已保存或未保存配置检测连通性 | 支持单项与批量检测 | GA |
| 同步预览 | 分页检索待入库候选补丁 | 当前支持 Windows 更新服务及三类 Linux 软件源 | GA |
| 选择入库 | 选择候选项写入补丁库 | 候选项不能为空，可覆盖严重级别 | GA |
| 源同步 | 从补丁源同步补丁元数据 | Windows 与 Linux 分别执行对应同步流程 | GA |

> 证据来源：server/apps/patch_mgmt/views/patch_source.py:87-97，server/apps/patch_mgmt/views/patch_source.py:338-365　|　同步基线：d2769559　|　【已实现】

对应产品：[[patch-management-product.md#设置]]、[[patch-management-product.md#补丁库]]

相关架构：[[patch-management-architecture.md#组件与职责]]

### 3. 补丁库

| 功能项 | 功能说明 | 规格 / 约束 | 状态 |
|---|---|---|---|
| 补丁列表与筛选 | 查看并筛选 Windows、Linux 补丁 | 展示严重级别、来源、适用范围及包状态 | GA |
| 补丁维护 | 新增、编辑、删除补丁 | 被基线引用或处于治理中的补丁不可删除 | GA |
| Windows 补丁包上传 | 上传或替换 Windows 安装包 | 未选择文件时拒绝操作 | GA |
| 补丁详情 | 查看平台通用属性及操作系统专属信息 | Windows 与 Linux 使用不同适用信息 | GA |

> 证据来源：server/apps/patch_mgmt/views/patch.py:38-135，server/apps/patch_mgmt/models/patch.py:29-181　|　同步基线：d2769559　|　【已实现】

对应产品：[[patch-management-product.md#补丁库]]

相关架构：[[patch-management-architecture.md#组件与职责]]

### 4. 目标管理

| 功能项 | 功能说明 | 规格 / 约束 | 状态 |
|---|---|---|---|
| 手工纳管 | 手工录入 Windows 或 Linux 主机 | 连接参数随操作系统类型变化 | GA |
| 节点批量纳入 | 从节点管理批量创建目标 | 至少选择一个节点 | GA |
| 目标维护 | 查看、编辑和删除目标 | 连接信息变化后重新检测连通性 | GA |
| 连通性检测 | 对目标连接进行检测 | 支持新建前检测与已保存目标检测 | GA |
| 基线与合规展示 | 展示当前基线、合规状态和最后评估时间 | 支持跳转查看主机风险 | GA |

> 证据来源：server/apps/patch_mgmt/views/patch_target.py:57-196，server/apps/patch_mgmt/models/patch_target.py:28-107　|　同步基线：d2769559　|　【已实现】

对应产品：[[patch-management-product.md#目标管理]]

相关架构：[[patch-management-architecture.md#执行拓扑]]

### 5. 基线管理

| 功能项 | 功能说明 | 规格 / 约束 | 状态 |
|---|---|---|---|
| 基线维护 | 创建、查看、编辑和删除基线 | Windows 与 Linux 基线分别维护 | GA |
| 补丁要求 | 向基线添加或移除补丁要求 | 同一基线内同一补丁不重复 | GA |
| 主机绑定 | 将主机绑定到基线 | 一台主机同时最多绑定一个基线 | GA |
| 合规分布 | 查看已绑定主机和合规状态 | 变更要求或绑定后旧评估结果失效 | GA |
| 基线评估 | 对基线已绑定主机发起评估 | 无要求或无主机时不可评估 | GA |
| 执行期保护 | 治理执行期间保护基线不被修改 | 存在活动治理任务时禁止变更 | GA |

> 证据来源：server/apps/patch_mgmt/models/baseline.py:10-141，server/apps/patch_mgmt/views/baseline.py:71-330　|　同步基线：d2769559　|　【已实现】

对应产品：[[patch-management-product.md#基线管理]]

相关架构：[[patch-management-architecture.md#数据与状态]]

### 6. 风险治理

| 功能项 | 功能说明 | 规格 / 约束 | 状态 |
|---|---|---|---|
| 多视角风险 | 按补丁、主机或基线聚合风险 | 仅展示同时具备相关数据权限的风险 | GA |
| 风险筛选与详情 | 查看影响范围、严重级别和治理状态 | 只基于当前有效的缺失项；未知和不适用项不生成风险 | GA |
| 风险修复 | 对选择的风险项创建安装任务 | 主机必须绑定包含所选补丁的基线 | GA |
| 执行安排 | 选择立即执行或执行窗口 | 同一主机的立即任务互斥 | GA |
| 重启治理 | 对待重启主机安排重启 | 必须指定执行窗口 | GA |
| 自动验证 | 安装成功且无需重启时自动验证；需要重启时，主机完成重启并恢复后自动验证 | 安装失败不会创建自动验证任务；验证结果刷新合规状态；安装或重启超时先只读核验，避免重复执行 | GA |
| 当前页风险导出 | 导出当前页已加载的风险数据 | 导出范围为当前页已加载数据，不承诺全量风险导出 | GA |
| 勾选聚合项导出 | 导出用户勾选的聚合风险项 | 未勾选项不可导出 | GA |
| 汇总与明细工作簿 | 在同一工作簿中提供风险汇总与明细 | 汇总中的“查看明细”跳转该项首条明细；不同语言及名称含引号时仍可正常跳转 | GA |

> 证据来源：server/apps/patch_mgmt/services/risk_service.py:299-333；server/apps/patch_mgmt/services/governance_convergence.py:47-113；server/apps/patch_mgmt/services/patch_execution_service.py:1874-1883,1974-2012；server/apps/patch_mgmt/tasks.py:346-386；web/src/app/patch-manager/(pages)/risk-pending/page.tsx:141-167,578-680,771-776；web/src/app/patch-manager/utils/worksheet-hyperlink.ts:1-10　|　同步基线：b98b782a7　|　【已实现】

对应产品：[[patch-management-product.md#风险治理]]

相关架构：[[patch-management-architecture.md#治理数据流]]

> 范围待确认：风险页按钮显示“导出全部”，而当前实现仅导出当前页已加载数据，不等同于全量风险导出。

### 7. 执行记录

| 功能项 | 功能说明 | 规格 / 约束 | 状态 |
|---|---|---|---|
| 任务列表与详情 | 查看用户发起的安装与重启根记录、进度、主机阶段和日志 | 详情按主机实时状态投影并收敛父任务；执行记录以执行栅栏防止陈旧执行覆盖当前状态 | GA |
| 任务取消 | 取消尚未下发的主机操作 | 必须填写原因；已下发操作不会被中断 | GA |
| 主机重试 | 对失败、未知或未满足的主机重试 | 必须指定重试目标 | GA |
| 记录导出 | 导出全部或选中的执行记录 | 导出范围受数据权限约束 | GA |

> 证据来源：server/apps/patch_mgmt/models/governance.py:121-134，server/apps/patch_mgmt/services/governance_convergence.py:47-113，server/apps/patch_mgmt/services/execution_record_service.py:211-264　|　同步基线：d2769559　|　【已实现】

对应产品：[[patch-management-product.md#风险治理]]

相关架构：[[patch-management-architecture.md#治理数据流]]

### 8. 周期评估设置

| 功能项 | 功能说明 | 规格 / 约束 | 状态 |
|---|---|---|---|
| 周期启停 | 启用或关闭周期评估 | 全局单例配置 | GA |
| 小时周期 | 按固定小时间隔执行评估 | 间隔至少一小时；只有已绑定基线的目标产生合规结果 | GA |
| 每日周期 | 按每日指定时间执行评估 | 时间采用小时和分钟 | GA |
| 每周周期 | 按周几和指定时间执行评估 | 周一至周日 | GA |

> 证据来源：server/apps/patch_mgmt/models/scan_setting.py:9-46，server/apps/patch_mgmt/views/scan_setting.py:24-40，server/apps/patch_mgmt/serializers/scan_setting.py:59-89，server/apps/patch_mgmt/tasks.py:65-94　|　同步基线：d2769559　|　【已实现】

对应产品：[[patch-management-product.md#设置]]

相关架构：[[patch-management-architecture.md#组件与职责]]

## 三、能力边界与约束

- 当前补丁源范围为 Windows 更新服务及 yum、dnf、apt 软件源。
- 风险基于当前有效的主机—基线评估状态；存在逐要求快照时以快照判断具体补丁风险。
- 基线当前只有生效中的固定清单，不提供历史版本管理。
- Windows 已安装的替代 KB 可满足对应基线要求；替代关系由 WSUS 同步关系映射。
- “不适用”状态不列为生产已实现能力：生产 Windows 解析当前不生成该事实，相关评估器与模型预留仍待确认。
- 功能清单不包含漏洞情报检索、任意第三方补丁源自动发现等未实现能力。

> 证据来源：server/apps/patch_mgmt/services/wsus_sync.py:343-365，server/apps/patch_mgmt/services/assess_parsers.py:240-250，server/apps/patch_mgmt/services/assess_parsers.py:288-317，server/apps/patch_mgmt/services/compliance_evaluator.py:142-198　|　同步基线：d2769559　|　【已实现/待确认】

## 四、平台协同

- 从节点管理纳入主机，并复用节点信息确定主机身份和连接路径。
- 复用平台 RPC 执行器与节点管理的云区域、节点能力完成评估、安装和重启操作。
- 复用系统管理的组织（组）与数据权限控制资源可见范围。
- 使用平台对象存储保存 SSH 私钥和手工上传的 Windows 补丁包。

> 证据来源：server/apps/patch_mgmt/models/patch_target.py:28-101，server/apps/patch_mgmt/models/patch.py:19-26，server/apps/patch_mgmt/services/patch_execution_service.py:36-40，server/apps/patch_mgmt/services/patch_execution_service.py:78-154，server/apps/core/backends.py:323-331，server/config/components/minio.py:19-28　|　同步基线：d2769559　|　【已实现】

## 五、支持范围

| 类别 | 当前范围 | 状态 |
|---|---|---|
| 操作系统 | Windows、Linux | GA |
| 补丁源 | WSUS、yum repo、dnf repo、apt repo | GA |
| 补丁类型 | 安全补丁、通用补丁 | GA |
| 严重级别 | 严重、重要、中等、低、未指定 | GA |
| 治理任务 | 评估、安装、重启、验证 | GA |
| 执行方式 | 立即执行、执行窗口 | GA |
| 重启策略 | 不自动重启、安装后自动重启；人工重启使用执行窗口 | GA |

> 证据来源：server/apps/patch_mgmt/constants/choices.py:4-266，server/apps/patch_mgmt/models/governance.py:13-65　|　同步基线：d2769559　|　【已实现】
