# 补丁管理 · 产品能力

补丁管理面向需要持续识别、评估和治理主机补丁风险的运维团队，形成“补丁源接入 → 补丁入库 → 主机纳管 → 基线绑定 → 合规评估 → 风险治理 → 结果验证”的闭环。本文件只描述当前代码已实现的产品能力。

相关架构：[[patch-management-architecture.md#模块职责]]

对应功能清单：[[patch-management-function-list.md#二、功能清单]]

## 产品入口

### 首页

首页集中展示纳管主机、评估覆盖率（按已绑定基线主机统计）、合规情况、待治理风险和异常数量，并提供合规分布、最近任务及高频风险概览。用户可从首页发起一次覆盖全部纳管主机的即时评估。

> 证据来源：web/src/app/patch-manager/(pages)/home/page.tsx:103-143，web/src/app/patch-manager/(pages)/home/page.tsx:201-313　|　同步基线：d2769559　|　【已实现】

对应功能清单：[[patch-management-function-list.md#1. 首页与评估概览]]

相关架构：[[patch-management-architecture.md#接口契约]]

### 风险治理

用户可从补丁、主机或基线三个视角查看当前有效风险，按条件筛选并查看影响范围、严重程度、合规状态和治理状态。逐项评估的数据契约预留满足、缺失、未知和不适用四态；当前生产取证实际生成满足、缺失和未知，不适用仅为模型与评估器预留【待确认】。只有已确认缺失且仍有效的要求进入风险，未知或不适用不被扩展为风险。选定风险后可安排立即修复或执行窗口，并为待重启主机创建重启窗口。

执行记录保留任务进度、主机级阶段、风险项和日志，支持取消尚未下发的主机操作，以及对失败、未知或未满足的主机重新执行。超时信息以实时状态投影展示，安装或重启超时先进入只读核验，避免重复下发可能已生效的操作；历史陈旧记录可经人工触发的对账收敛，不会自动重跑。

用户可导出当前页已加载数据，或导出勾选的聚合风险项。导出工作簿包含汇总与明细：汇总中的“查看明细”可跳转至该项首条明细，并在不同语言及名称含引号时仍可正常跳转。界面按钮当前显示“导出全部”，但实际范围为当前页已加载数据而非全量风险，按钮名称与范围的一致性【待确认】。

> 证据来源：server/apps/patch_mgmt/services/risk_service.py:299-333；server/apps/patch_mgmt/services/execution_record_service.py:211-264；server/apps/patch_mgmt/services/governance_convergence.py:47-113,139-234；web/src/app/patch-manager/(pages)/risk-pending/page.tsx:141-167,578-680,771-776；web/src/app/patch-manager/utils/worksheet-hyperlink.ts:1-10　|　同步基线：b98b782a7　|　【已实现/待确认】

对应功能清单：[[patch-management-function-list.md#6. 风险治理]]

相关架构：[[patch-management-architecture.md#治理数据流]]

### 补丁库

补丁库统一维护 Windows 与 Linux 补丁，支持检索、查看、新增、编辑和删除。Windows 补丁可以上传或替换安装包；从补丁源同步时，用户可先预览候选项，再选择需要入库的补丁并调整严重级别。

被基线引用或正在治理的补丁不可删除，避免治理依据在执行期间发生漂移。

> 证据来源：server/apps/patch_mgmt/views/patch.py:38-135，server/apps/patch_mgmt/views/patch_source.py:197-281，web/src/app/patch-manager/(pages)/library/page.tsx:251-328，web/src/app/patch-manager/(pages)/library/page.tsx:344-749　|　同步基线：d2769559　|　【已实现】

对应功能清单：[[patch-management-function-list.md#3. 补丁库]]

相关架构：[[patch-management-architecture.md#组件与职责]]

### 基线管理

用户可分别为 Windows 或 Linux 创建补丁基线，向基线添加补丁要求并绑定主机。一台主机同时最多绑定一个基线；重新绑定时以新基线为准。

基线要求或主机绑定发生变化后，旧评估结果失效，相关主机回到待评估状态。基线无补丁要求或未绑定主机时不能发起评估；存在进行中的治理任务时不能修改基线。

> 证据来源：server/apps/patch_mgmt/models/baseline.py:10-16，server/apps/patch_mgmt/models/baseline.py:73-118，server/apps/patch_mgmt/views/baseline.py:71-330　|　同步基线：d2769559　|　【已实现】

对应功能清单：[[patch-management-function-list.md#5. 基线管理]]

相关架构：[[patch-management-architecture.md#数据与状态]]

### 目标管理

用户可手工录入 Windows 或 Linux 主机，也可从节点管理批量纳入主机。目标列表展示操作系统、架构、来源、连通性、当前基线和最近合规状态，并支持编辑、删除、连通性检测及跳转查看主机风险。

连接信息变化后，系统会重新确认连通性，避免沿用旧连接结果。

> 证据来源：server/apps/patch_mgmt/views/patch_target.py:57-196，web/src/app/patch-manager/(pages)/target/page.tsx:412-666，web/src/app/patch-manager/(pages)/target/page.tsx:748-759　|　同步基线：d2769559　|　【已实现】

对应功能清单：[[patch-management-function-list.md#4. 目标管理]]

相关架构：[[patch-management-architecture.md#执行拓扑]]

### 设置

设置页维护补丁源和全局评估周期。补丁源支持新增、编辑、删除、启停和连通性检测；当前支持 Windows 更新服务以及 Linux 的三类主流软件源。自定义补丁源创建时会归属到当前可信团队，同步和查看均按该归属校验。同步候选预览和选择入库在补丁库完成。

周期评估可启停，并可按小时、每日或每周安排；调度时区取用户 IANA 时区，并可按规则发送周期评估通知。关闭周期评估不影响用户手工发起评估。

> 证据来源：server/apps/patch_mgmt/models/scan_setting.py:33-41，server/apps/patch_mgmt/views/scan_setting.py:24-40　|　同步基线：61bace9f　|　【已实现】

对应功能清单：[[patch-management-function-list.md#2. 补丁源]]、[[patch-management-function-list.md#8. 周期评估设置]]

相关架构：[[patch-management-architecture.md#组件与职责]]

## 核心业务流程

1. 管理员配置补丁源并验证连通性。
2. 管理员预览同步候选项，将需要治理的补丁纳入补丁库。
3. 管理员纳管目标主机并确认连接可用。
4. 管理员建立补丁基线、添加补丁要求并绑定主机。
5. 系统按手工触发或周期安排执行合规评估。
6. 用户从风险视图选择风险项，安排安装和可选的重启策略。
7. 系统记录每台主机的执行阶段；完成后再次验证并刷新合规结果。

> 证据来源：server/apps/patch_mgmt/models/governance.py:13-65，server/apps/patch_mgmt/tasks.py:65-199，server/apps/patch_mgmt/tasks.py:454-578　|　同步基线：d2769559　|　【已实现】

## 业务规则与边界

- 风险基于当前有效的“主机—基线”评估状态；存在逐要求合规快照时，以快照判断具体补丁风险。未配置、待评估或已失效的结果不作为当前风险。
- 风险可见性受主机、补丁和基线三类数据范围交集约束；治理提交复核所选主机与补丁权限，并校验补丁属于主机当前基线。
- 立即治理时，同一主机不能并发进入多个活动任务；执行窗口内的任务按窗口约束等待执行。
- 重启只面向处于待重启状态的主机，并要求明确执行窗口。
- 即时或周期评估任务可覆盖纳管目标，但只有已绑定基线的目标产生合规结果并刷新风险。
- Windows 评估会识别已安装的替代 KB：从 Windows 更新服务同步到的替代关系会映射为补丁替代关系，并与目标机已安装更新共同判断要求是否满足。Windows 当前生产采集不会产生“不适用”事实；该状态虽被评估器和数据模型预留，但不能据此向用户承诺“不适用”的自动判定。【待确认】
- 当前不承诺漏洞情报检索、自动发现任意第三方补丁源，或支持 Windows 更新服务及三类 Linux 软件源以外的同步协议。

> 证据来源：server/apps/patch_mgmt/services/wsus_sync.py:343-365，server/apps/patch_mgmt/services/assess_parsers.py:240-250，server/apps/patch_mgmt/services/assess_parsers.py:288-317，server/apps/patch_mgmt/services/compliance_evaluator.py:142-198　|　同步基线：d2769559　|　【已实现/待确认】
