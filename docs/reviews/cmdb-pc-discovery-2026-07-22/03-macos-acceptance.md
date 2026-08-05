# PC 发现 macOS 真实环境验收

> 状态：**未执行（本环境无可用 macOS SSH 目标机）**。
> 本文件列出发布前必须在真实 macOS 环境完成的验收清单与记录格式；
> 离线合同证据见 `01-test-evidence.md`。任何一项不得用 fixture 或 mock 代替。

## 环境前提

- 至少一台 Intel 或 Apple Silicon macOS，开启远程登录（SSH）；
- 三种凭据形态各验证一轮：密码、PEM 私钥、私钥+密码短语；
- 记录实际架构（Intel x86_64 / Apple Silicon arm64）；未覆盖的另一架构明确标记"未验证"；
- 每次运行记录：任务 ID、snapshot ID、PC inst_name、前后软件实例 ID、ChangeRecord ID；
- 记录中不得出现任何凭据（口令、私钥正文、密码短语）。

## 验收清单

| # | 场景 | 通过标准 | 状态 |
|---|---|---|---|
| M1 | SSH 密码认证首次采集 | PC 落库，inst_name = `MAC-<IOPlatformUUID>`，白名单字段完整 | 未验证 |
| M2 | PEM 私钥认证 | 采集成功，私钥只经 env_config 注入，日志/VM/审计无正文 | 未验证 |
| M3 | 私钥+密码短语认证 | 采集成功；密码短语不进入任何链路产物 | 未验证 |
| M4 | 身份稳定性 | 修改 IP/主机名后再采集，不新建 PC，原实例更新 | 未验证 |
| M5 | `/Applications` 软件枚举 | .app 落库，macOS 优先 Bundle ID 作为 software_key | 未验证 |
| M6 | 安装新软件 | 下一轮快照新增 pc_software 实例并建立 install_on 关联 | 未验证 |
| M7 | 升级软件 | 同一 inst_name 版本字段更新，不新建实例 | 未验证 |
| M8 | 卸载软件 | 完整快照 + `immediately` 策略下差集删除，写 DELETE_INST 审计 | 未验证 |
| M9 | 完整空快照 | 仅删除该 PC 名下全部软件，PC 实体保留 | 未验证 |
| M10 | 错误凭据 | 错误码 SSH_AUTH_FAILED，无任何写入/删除 | 未验证 |
| M11 | 私钥无效/密码短语错误 | 错误码 SSH_KEY_INVALID | 未验证 |
| M12 | SSH 服务关闭 | 错误码 TARGET_UNREACHABLE，既有数据保留 | 未验证 |
| M13 | 采集超时 | 错误码 SCRIPT_TIMEOUT，无部分写入 | 未验证 |
| M14 | 连接测试按钮 | 返回 os_type=macos 与 inst_name；目标机无写入、CMDB 无写入 | 未验证 |
| M15 | 只读复核 | 采集前后文件系统无写入变化；脚本仅 ioreg/sw_vers/scutil/目录枚举 | 未验证 |
| M16 | 架构覆盖 | Intel 与 Apple Silicon 各一轮；未覆盖架构标"未验证" | 未验证 |

## 执行记录

（待真实环境执行后填写：日期、执行人、目标机 macOS 版本与芯片、每场景证据链接/截图编号）
