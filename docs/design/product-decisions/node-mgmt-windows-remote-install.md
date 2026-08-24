# 节点管理 Windows 远程安装产品决策记忆

- 最近更新：2026-08-24
- 当前规格：`specs/changes/windows-controller-remote-install/spec.md`

## 产品定位

Windows 控制器远程安装面向可信内网批量交付 sidecar，不替代手工 GUI 安装，也不自动改目标机 WinRM / 防火墙 / 证书。

## 已确认范围

- 安装和卸载都支持用户显式选择 WinRM HTTP。
- 默认仍为 HTTPS + NTLM + 5986。
- 安装会话 URL 和 bootstrap 回 Server 拉包继续只接受 HTTPS。

## 已确认设计决策

- WinRM HTTP 是 opt-in，不是默认值；不得把现网 HTTPS 安装无声改成明文。原因：现场大量 Windows 只有 HTTP/5985，但安装通道会传输管理员认证材料和短时会话 URL，默认明文不可接受。
- HTTPS+5985、HTTP+5986 在提交时拒绝，不等 Ansible `UNREACHABLE`。
- 证书校验开关只对 HTTPS 生效；选择 HTTP 时强制关闭校验并展示更重的明文风险提示。
- Basic、Kerberos、CredSSP、自动开启目标机 HTTPS Listener 仍不开放。
- 「检查登录凭据配置」只校验表单完整性，不探测 WinRM 连通性。

## 明确后置

- 安装前由 Executor 做真实连通性探测。
- 把 HTTP 做成默认协议。
- 开放 Basic / Kerberos / CredSSP。

## 仍待确认

无

## 已替代决策

- 2026-08-24：第一版「WinRM 只开放 HTTPS，HTTP 不开放」被替代。替代原因：该收口与可信内网 + 默认关证书校验的威胁模型不一致，且阻断只开 5985 的现场批量交付。安装会话 HTTPS 禁令未替代。

## 决策来源

- GitHub issue #4946
- 2026-08-24 产品确认：安装和卸载都要支持可选 HTTP
