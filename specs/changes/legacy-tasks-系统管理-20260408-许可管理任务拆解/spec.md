# 系统管理-许可管理任务拆解

Status: cancelled

> Migrated from `spec/tasks/系统管理/20260408.许可管理任务拆解.md` as historical change evidence.

日期：2026-04-08

关联文档：

- Requirements：`spec/requirements/系统管理/20260407.许可管理.md`
- Solution Plan：`spec/solution_plan/系统管理/20260407.许可管理.md`
- Tech Plan：`spec/tech_plan/系统管理/20260408.许可管理.md`

## 目标

将“许可管理”从文档方案拆解为可执行开发任务，供后续按阶段推进研发。本文档仅用于任务拆分与排期，不包含代码实现。

## 拆解原则

- 先完成前后端企业版隔离与基础接入，再进入业务实现。
- 后端优先打底，前端跟随后端稳定接口推进。
- 公共接入点与企业版业务实现分开跟踪，避免遗漏跨模块改造。
- 对外部依赖项和跨模块协作项单独标注，防止研发中后期返工。

---

## 阶段一：文档与边界冻结

### 任务 1.1：确认三份核心文档冻结版本

- 目标：以当前 requirements / solution_plan / tech_plan 作为开发基线。
- 输入：现有三份文档。
- 输出：开发阶段统一引用文档版本。
- 验收：团队对业务边界、技术边界、前后端企业版隔离方案无歧义。

### 任务 1.2：确认企业版前后端代码目录约束

- 目标：明确后端使用 `server/apps/license_mgmt`，前端使用 `web/src/app/system-manager/enterprise`。
- 输出：研发过程中的目录使用约束。
- 验收：后续开发不将许可管理真实业务代码写入社区版路径。

### 任务 1.3：确认剩余技术 TODO 的责任人

- 目标：为下列事项指定负责人与确认时点。
- 范围：
  - `settings.LICENSE_PUBLIC_KEYS` 配置格式与轮换流程
  - 各模块新增资源入口在 `LICENSE_APP_PERMISSIONS` 中的最终配置内容
- 验收：每个 TODO 都有明确 owner。

---

## 阶段二：后端企业版应用骨架

### 任务 2.1：建立 `license_mgmt` 企业版独立 app 目录

- 目标：创建 `apps.py / urls.py / models / serializers / services / viewset / migrations / config.py / nats_api.py` 基础结构。
- 输出：可注册的 Django app 骨架。
- 验收：企业版 `INSTALLED_APPS` 可注册该 app，社区版不受影响。

### 任务 2.2：建立 `apps.rpc.license_mgmt` RPC 封装

- 目标：为注册码读取、许可校验等 NATS 能力提供统一调用封装。
- 输出：`server/apps/rpc/license_mgmt.py`
- 验收：其他模块可通过统一 RPC 入口调用 `license_mgmt`。

### 任务 2.3：建立 `config.py` 配置接入

- 目标：在 `license_mgmt/config.py` 中定义 `LICENSE_APP_PERMISSIONS` 等大写配置项，接入 `server/config/components/extra.py` 自动加载机制。
- 输出：配置结构与默认值。
- 验收：配置可进入 `django.conf.settings`。

---

## 阶段三：注册码与许可解析能力

### 任务 3.1：约定注册码来源文件

- 目标：统一注册码来源为 `server/apps/license_mgmt/registration_code.py`。
- 输出：模块级 `registration_code` 变量。
- 验收：服务端可稳定读取注册码明文。

### 任务 3.2：提供注册码读取接口

- 目标：通过 `license_mgmt` 接口返回注册码展示值。
- 输出：`GET /api/v1/license_mgmt/license/registration-code/`
- 验收：前端可读取并复制注册码，底层实现细节不暴露。

---

## 阶段四：许可主数据与解析能力

### 任务 4.1：实现许可核心模型

- 目标：实现 `LicenseRecord / LicenseGlobalReminderConfig / LicenseReminderOverride / ModuleReminderConfig / NodeReminderOverride`。
- 输出：模型与 migration。
- 验收：迁移独立、字段符合 tech plan。

### 任务 4.2：实现许可码解析与验签服务

- 目标：在 `license_decode_service.py` 中实现：
  - 若输入为 `.lic` 文件内容字符串，先使用注册码解外层
  - `base64url` 解码
  - canonical JSON
  - `Ed25519` 验签
  - `nbf / exp` 时间校验
  - `payload.reg` 与注册码一致性校验
- 输出：许可解析服务。
- 验收：合法许可可导入，非法签名、过期许可、注册码不匹配均被拒绝。

### 任务 4.3：实现许可新增接口

- 目标：新增许可并写入许可主数据。
- 输出：`POST /api/v1/license_mgmt/license/`
- 验收：导入成功后许可列表可见，模块范围正确落库。

### 任务 4.4：实现许可列表 / 历史许可 / 停用接口

- 输出：
  - 生效许可列表接口
  - 历史许可列表接口
  - 停用接口
- 验收：停用后进入历史许可；历史仅包含手动停用和已到期许可。

### 任务 4.5：实现模块授权摘要接口

- 目标：基于许可内容返回免激活 / 已激活 / 未激活模块摘要。
- 输出：模块授权汇总接口。
- 验收：页面可直接使用该接口展示模块状态与数量。

---

## 阶段五：提醒配置能力

### 任务 5.1：实现全局默认提醒接口

- 目标：支持默认通知渠道、默认通知人员、默认提醒时间的读取与保存。
- 输出：全局提醒接口。
- 验收：支持多渠道、多人员、多天数保存与回显。

### 任务 5.2：实现单许可提醒接口

- 目标：支持 `follow / custom` 两种模式。
- 输出：单许可提醒读取与保存接口。
- 验收：默认摘要与单独配置均可正确回显。

### 任务 5.3：实现节点提醒接口

- 目标：支持模块级默认阈值与专用节点类型覆盖。
- 输出：节点提醒读取与保存接口。
- 验收：同一模块下对象类型不可重复配置。

### 任务 5.4：实现日志容量提醒接口

- 目标：支持 `follow / custom` 两种模式。
- 输出：日志容量提醒读取与保存接口。
- 验收：阈值校验生效，回显正确。

### 任务 5.5：接入通知渠道与通知人员可见范围校验

- 目标：保证通知渠道和通知人员都只来自“当前用户拥有权限组下的可见范围”。
- 输出：统一校验逻辑。
- 验收：越权数据不可提交、不可回显。

---

## 阶段六：新增资源许可校验能力

### 任务 6.1：实现 `LICENSE_APP_PERMISSIONS` 配置读取服务

- 目标：由 `permission_guard_service` 从 settings 中读取各模块校验入口定义。
- 输出：统一配置读取与匹配逻辑。
- 验收：可识别 `cmdb / node_mgmt / monitor / log` 的配置项。

### 任务 6.2：实现 `license_mgmt` NATS 校验接口

- 目标：暴露 `validate_module_create_access(module_code)`。
- 输出：`license_mgmt.nats_api`
- 验收：外部模块可通过 RPC 获取统一校验结果。

### 任务 6.3：实现统一许可校验中间件

- 目标：在中间件中完成：
  - `LICENSE_MGMT_ENABLED` 判定
  - 新增资源请求识别
  - 配置匹配
  - NATS 校验调用
- 输出：`license_guard.py`
- 验收：命中配置时可阻断新增请求，未命中时不影响现有请求。

### 任务 6.4：组织四个模块补齐权限配置内容

- 范围：
  - `node_mgmt`
  - `cmdb`
  - `monitor`
  - `log`
- 目标：由各模块补齐自身新增资源入口定义。
- 验收：四个模块的配置已录入 `LICENSE_APP_PERMISSIONS`。

---

## 阶段七：前端企业版页面实现

### 任务 7.1：在 enterprise 目录下建立许可管理前端骨架

- 路径：`web/src/app/system-manager/enterprise/`
- 输出：`api / types / (pages) / components`
- 验收：企业版前端目录结构建立完成。

### 任务 7.2：实现许可列表与历史许可视图

- 输出：许可列表卡片、历史许可抽屉。
- 验收：支持列表展示、状态展示、停用入口与历史查看。

### 任务 7.3：实现默认提醒与单许可提醒交互

- 输出：默认提醒面板、单许可提醒弹窗。
- 验收：支持 `follow / custom`、渠道多选、人员多选、提醒时间编辑。

### 任务 7.4：实现平台模块与额度视图

- 输出：模块授权状态区、对象节点额度抽屉。
- 验收：支持模块汇总、额度状态和重新统计入口展示。

### 任务 7.5：实现节点提醒与日志容量提醒交互

- 输出：节点提醒弹窗、日志容量提醒弹窗。
- 验收：支持默认摘要、单独配置、阈值校验与回显。

### 任务 7.6：实现注册码展示与许可新增交互

- 输出：添加许可弹窗、注册码展示与复制、许可码提交。
- 验收：新增成功后刷新许可列表。

---

## 阶段八：联调与验收

### 任务 8.1：后端单元测试与集成测试补齐

- 目标：覆盖 tech plan 中列出的后端测试点。
- 验收：核心链路测试通过。

### 任务 8.2：前端联调验证

- 目标：完成页面交互、回显、刷新与权限验证。
- 验收：前端验收项全部通过。

### 任务 8.3：企业版发布前检查

- 检查项：
  - `license_mgmt` app 注册
  - migration 顺序
  - `registration_code.py` 已按部署要求覆盖
  - 菜单初始化判断
  - 超管可见、普通用户不可见
- 验收：满足直接上线条件。

---

## 外部依赖 / 协作项

- 协作项 1：明确 `settings.LICENSE_PUBLIC_KEYS` 配置格式与公钥轮换策略。
- 协作项 2：四个业务模块补齐 `LICENSE_APP_PERMISSIONS` 中的各自入口定义。
- 协作项 3：确认 `registration_code.py` 在部署环境中的覆盖方式与发布校验策略。

---

## 建议执行顺序

1. 先做阶段一、二、三，完成骨架与注册码能力。
2. 再做阶段四、五，完成许可主数据与提醒接口。
3. 然后做阶段六，完成跨模块新增资源校验。
4. 最后做阶段七、八，完成前端页面、联调与发布准备。
