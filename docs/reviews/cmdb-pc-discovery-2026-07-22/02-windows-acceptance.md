# PC 发现 Windows 真实环境验收

> 状态：**未执行（本环境无 Windows 10/11 WinRM 目标机）**。
> 本文件列出发布前必须在真实 Windows 环境完成的验收清单与记录格式；
> 离线合同证据见 `01-test-evidence.md`。任何一项不得用 fixture 或 mock 代替。

## 环境前提

- Windows 10 与 Windows 11 各至少一台；WinRM 服务可用；
- 默认链路 HTTPS/5986 + NTLM（自签证书，`cert_validation=false`）；
- 若发布 HTTP/5985，再单独一台或单独一轮验证，并截图前端安全警告；
- 每次运行记录：任务 ID、snapshot ID、PC inst_name、前后软件实例 ID、ChangeRecord ID；
- 记录中不得出现任何凭据。

## 验收清单

| # | 场景 | 通过标准 | 状态 |
|---|---|---|---|
| W1 | WinRM HTTPS/5986 + NTLM 首次采集 | PC 落库，inst_name = `WIN-<硬件UUID>`（UUID 无效时 `WIN-SN-<序列号>`），白名单字段完整 | 未验证 |
| W2 | 身份稳定性 | 修改 IP/主机名后再采集，不新建 PC，原实例更新 | 未验证 |
| W3 | 硬件信息 | hardware_uuid/serial_number/device_model 与目标机 `Win32_ComputerSystemProduct` 一致 | 未验证 |
| W4 | 软件枚举（HKLM 32/64 位） | 两侧注册表视图软件均落库，software_key = `name\|publisher` 规范化 | 未验证 |
| W5 | 安装新软件 | 下一轮快照新增 pc_software 实例并建立 install_on 关联 | 未验证 |
| W6 | 升级软件 | 同一 inst_name 版本字段更新，不新建实例 | 未验证 |
| W7 | 卸载软件 | 完整快照 + `immediately` 策略下差集删除，写 DELETE_INST 审计 | 未验证 |
| W8 | 完整空快照（卸载全部软件） | 仅删除该 PC 名下全部软件，PC 实体保留，其他 PC 不受影响 | 未验证 |
| W9 | 错误密码 | 任务结果错误码 WINRM_AUTH_FAILED，无任何写入/删除 | 未验证 |
| W10 | 端口阻断/目标不可达 | 错误码 TARGET_UNREACHABLE，既有数据保留 | 未验证 |
| W11 | WinRM 服务关闭 | 同上，稳定错误码，无部分写入 | 未验证 |
| W12 | HTTP/5985（如发布） | 前端显示明文传输安全警告；任务 params 记录 `security_warning=WINRM_HTTP_INSECURE` | 未验证 |
| W13 | 连接测试按钮 | 表单未落库状态直连，返回 os_type 与 inst_name；目标机无写入、CMDB 无写入 | 未验证 |
| W14 | 只读复核 | 采集前后注册表/文件系统无写入变化（对照快照或审计工具） | 未验证 |
| W15 | 资源边界 | 软件超 5000 条或输出超 10MB 时降级 partial，不删除、目标机不崩溃 | 未验证 |

## 执行记录

（待真实环境执行后填写：日期、执行人、目标机 OS 版本、每场景证据链接/截图编号）
