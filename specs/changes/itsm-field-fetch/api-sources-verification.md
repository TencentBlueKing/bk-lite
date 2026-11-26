# 网关、外部 API 与表单测试数据

## 行为

- 字段 API 下拉可搜索平台完整查询目录；当前本地目录有 46 个查询接口。显式选择后复用或创建同域集成引用，实际执行仍由平台 dispatcher 校验调用者权限。
- 集成页区分平台网关与外部 API。外部接口支持 URL、HTTP 方法、Bearer Token、输入参数类型/必填/说明，令牌加密保存且不回传。
- 外部 GET 可用于表单取数；其他方法只用于流程 API 节点/显式调试。复用 safe_request：网络白名单、DNS 固定、禁重定向、超时、1MB 响应上限。只接受 JSON 响应。
- 外部地址变化时不沿用旧认证令牌。表单发布仍固定集成配置快照，公开 schema 不暴露凭据。

## 本地测试服务

启动：在仓库根执行 `server/.venv/bin/python server/apps/itsm/devtools/form_demo_api.py`。
仅监听 `127.0.0.1:8096`，数据均为虚构，不连接数据库。

| GET 路径 | 返回内容 | 筛选 |
| --- | --- | --- |
| /departments | 3 个部门 | keyword、page、page_size |
| /assets | 12 台设备 | 上述参数，以及 department（rd/ops/finance）、environment（dev/test/prod） |
| /regions | 2 个地区及城市子节点 | keyword、page、page_size |
| /plans | 4 个套餐 | keyword、page、page_size |
| /health | 服务状态 | 无 |

返回数组路径 `data.items`，显示字段 `name`，选项值 `id`，级联子节点 `children`，数值列 `amount`。
已在 domain.com 插入 4 个 `[测试] 外部 API · …` 集成，新增精确回环地址白名单 `127.0.0.1/32` 以供本地服务联调；未放开其他网段。

## 测试数据

`cd server && .venv/bin/python manage.py seed_itsm_form_demo --domain domain.com`

重复执行不覆盖已有资源。创建 4 个字典（优先级、部署环境、地区与机房、故障分类）、2 张表（12 行设备台账、8 行服务套餐）和 2 个 Python 动作（按环境筛选、费用计算）。在下拉中搜索 `[测试]`。

## 页面实测

- 直接搜索并选择网关 `GET itsm/tickets`，测试样本与映射均成功，返回 1 个选项。
- 外部设备查询：样本自动识别 `data.items/name/id`，映射返回 12 个选项；department=rd 后返回 4 个选项。
- 新地区字典返回 3 个一级选项；新设备表映射返回 12 行。
- 后端真实 HTTP 调用四个本地外部 API 成功，分别返回 3/12/2/4 个一级记录。
- 集成页实际保存外部设备 API，再在线调试 `{"department":"ops","page_size":2}`：成功，total=4，items=2。
- ITSM 后端回归 377 项通过；新增的本地 HTTP 服务测试补跑通过。API 来源专项 16 项通过，外部请求模块覆盖率 90%，本地测试服务覆盖率 98%。
- ITSM 前端 76 项通过，完整 type-check 通过。全仓 lint 保留 3 个非 ITSM 既有错误，改动文件无新增 lint 错误。
