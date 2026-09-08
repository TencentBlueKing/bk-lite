# 华为 iBMC 风格 Redfish 模拟目标

用于讨论和开发“物理服务器 Redfish”配置采集插件。仅依赖 Python 标准库，TLS 证书生成额外需要 OpenSSL；不依赖 Docker、BMC、Postgres、Redis、NATS 或产品 Server。作为独立测试目标运行，不加入产品启动脚本、Supervisor 或 batch_init。

## 数据与证据范围

本目录是**合成协议模拟器**，不是华为固件仿真器、真机抓包、完整 Redfish 合规实现或厂商兼容认证。

公开资料核对于 2026-09-07：

- [华为官方 Huawei-iBMC-Cmdlets](https://github.com/Huawei/Huawei-iBMC-Cmdlets)：华为提供通过 Redfish 访问 iBMC 的工具；列出包括 2288H V5 和 TaiShan 200 在内的 x86/ARM 产品范围。该列表不是本插件已验证机型列表。
- [华为鲲鹏服务器 iBMC Redfish 接口说明](https://support.huawei.com/enterprise/zh/doc/EDOC1100372764/18bfdbec)：公开检索摘录说明机架系统 ID 可为 `1`，其他形态可能是 `BladeN` 等；正文访问返回 403，不能据此宣称已逐字段核对所有资源。
- [DMTF Redfish 协议规范](https://www.dmtf.org/sites/default/files/standards/documents/DSP0266_1.23.0.html)：资源链接、JSON、HTTP、认证和会话机制的参考。
- [DMTF 资源说明](https://redfish.dmtf.org/schemas/DSP2046_2020.4.html)：System、Manager、Chassis 及硬件资源字段参考。

`inventory.py` 使用标准 Redfish 字段生成虚构信息，所有序列号、型号后缀、固件版本明确带 `MOCK` 或 `synthetic`。Redfish/Schema 版本、容量、CPU 配置、资源路径布局是测试选择，不表示某一华为固件实际行为。不编造 Huawei OEM 字段。`multi-system` 混合 ID、跨 Chassis 的 Drive 链接和分页是鲁棒性用例，不代表 2288H V5 或 TaiShan 的实际拓扑。

| 参数 | 模拟内容 |
| --- | --- |
| `--profile x86` | 2288H V5 风格标签，2 个合成 x86 CPU |
| `--profile arm` | TaiShan 200 风格标签，2 个合成 ARM CPU |
| 两组共有 | 256 GiB 内存（8×32 GiB）、2 块 960 GB SSD、1 个 RAID1 逻辑卷、2 个 10G 主机网口、独立管理口 |
| `--scenario healthy` | 完整清单，默认场景 |
| `--scenario partial` | Storage 集合返回 404，其他资源正常 |
| `--scenario unauthorized` | 服务根可访问；保护资源和登录返回 401 |
| `--scenario unavailable` | Systems 集合返回 503 + Retry-After |
| `--scenario multi-system` | 两个 System，各有不同身份和磁盘容量，用于发现资源混归属、容量累计错误 |
| `--scenario paginated` | 内存集合分两页，使用 Members@odata.nextLink |

## 启动

从仓库根目录执行。需要 Python 3.8+，也可使用 `agents/stargazer/.venv/bin/python`。服务固定只监听 `127.0.0.1`；本机采集进程可访问，其他容器和远端接入点不能直接使用此环回地址。

```bash
cd agents/stargazer/tests/collect_fixtures/huawei_redfish_target

# 只用于这个模拟目标，密码输入不回显；不要使用设备真实凭据。
export REDFISH_MOCK_USERNAME=mock-reader
read -s REDFISH_MOCK_PASSWORD
export REDFISH_MOCK_PASSWORD

# 每次生成独立的短期测试证书，私钥不进入仓库。
REDFISH_MOCK_TLS_DIR=$(mktemp -d /tmp/redfish-mock-tls.XXXXXX)
openssl req -x509 -newkey rsa:2048 -nodes -days 1 \
  -keyout "$REDFISH_MOCK_TLS_DIR/key.pem" \
  -out "$REDFISH_MOCK_TLS_DIR/cert.pem" -config tls.cnf

python3 mock_server.py --profile x86 --scenario healthy \
  --cert "$REDFISH_MOCK_TLS_DIR/cert.pem" --key "$REDFISH_MOCK_TLS_DIR/key.pem"
```

默认地址：`https://127.0.0.1:18443/redfish/v1/`。Ctrl+C 停止，不留下后台进程。要改场景，停止后修改 `--profile` / `--scenario` 重启。重启会清空模拟登录会话，硬件清单身份保持稳定。

模拟目标的严格校验测试会将生成的 `cert.pem` 作为可信 CA，同时启用主机名校验。产品任务也允许明确关闭证书校验，用于验证自签证书场景；仅验证环回 HTTP 时，可显式运行：

```bash
python3 mock_server.py --http --port 18080 --profile arm --scenario paginated
```

Redfish 任务可填：BMC IP `127.0.0.1`、HTTPS 端口 `18443`、上述环境注入账号密码。任务默认校验 TLS 证书；使用该临时自签证书联调时，可明确关闭证书校验。HTTP 模式仅是本地模拟调试入口，不代表产品支持明文凭据传输。

## 接口行为

- `GET /redfish/v1/`：公开服务根，包含 Systems / Managers / Chassis / SessionService 链接。
- 清单 GET：接受 HTTP Basic 或有效 `X-Auth-Token`。
- `POST /redfish/v1/SessionService/Sessions`：JSON `UserName` / `Password`；返回 201、`Location`、`X-Auth-Token`。会话保存在内存，有效期 60 秒，最多 16 个。
- `DELETE <Location>`：使用本会话 token，返回 204；其他会话不能删除。
- PATCH / PUT / 硬件 DELETE / 电源等 POST：405，不改变清单。仅允许模拟认证会话创建与退出。
- 返回 `X-Mock-Data: synthetic-not-hardware-verified`。不记录密码、token、请求体或逐项访问日志。
- 并发连接最多 8 个；socket 超时 3 秒；登录请求体最多 4 KiB；清单规模固定。没有可远程修改场景或任意文件访问的入口。
- 暂不模拟 OEM、慢响应、固件历史数据、旧 TLS、设备限流细节、全部 Redfish 元数据和 Session 集合枚举；不宣称通过 DMTF Validator。

## 新鲜验证

从仓库根目录执行：

```bash
agents/stargazer/.venv/bin/python -m unittest discover \
  -s agents/stargazer/tests/collect_fixtures/huawei_redfish_target -p 'test_*.py' -v
```

测试会启动真实环回 HTTP/HTTPS 服务并在结束后关闭，TLS 私钥在临时目录生成并自动清理。若沙箱禁止 bind，需要允许环回端口测试。没有 OpenSSL 时 TLS 用例显示 skipped，不能算 TLS 已验证。

测试覆盖两组清单重复读取稳定、CPU 架构区分、所有硬件详情可访问、主机/管理网卡区分、跨路径 Drive、逻辑卷关联、多 System 隔离、分页、401/404/503、Basic 与 Token 鉴权、退出/过期、错误输入、会话容量上限和禁止硬件写入。这是模拟服务的验证，不是 CMDB 去重/同步或生产 collector 的验证。

2026-09-07 本机验证：10 项 unittest 全部通过，含 HTTPS（未跳过）；排除测试文件后的语句覆盖率 84%（inventory 98%、mock_server 80%）。新增 Python 文件的 Black / isort / flake8 检查通过。`cd agents/stargazer && make lint` 失败于现有入口缺少 `.pre-commit-config.yaml`，因此不能报告全模块 lint 通过。测试结束后服务已关闭，未留下常驻模拟进程。

## 当前插件实现范围

1. 用户入口：已增加与 SSH、IPMI 并列的“物理服务器 Redfish”，插件 ID 为 `physcial_server_redfish`，执行驱动为 `protocol`。
2. 协议分流：任务通过持久化参数 `collection_protocol=redfish` 进入 Redfish 采集器；新 IPMI 任务显式写 `ipmi`，历史无标记协议任务兼容为 IPMI。
3. 资产身份：SSH、IPMI、Redfish 都以采集目标 IP 生成同一个 `physcial_server.inst_name`。首次写入任务通过 `collect_task` 取得实例，其他任务受任务过滤与实例名唯一约束，不能更新或重复创建。
4. 第一阶段字段：只读取唯一 `ComputerSystem` 的 `SerialNumber`、`Model`、`Manufacturer`、`AssetTag`，连同目标 IP 和端口写入整机；暂不创建内存、磁盘、网卡等子实例。
5. 安全边界：只允许 HTTPS、Basic Auth、目标 IP 和同源 `/redfish/v1` 相对资源链接；证书校验默认开启并允许任务明确关闭，禁止重定向和系统代理，并限制连接数、超时和响应大小。
6. 验证状态：模拟目标和采集器自动化测试已完成；尚未获得华为或其他国内品牌真机，因此不能宣称机型兼容认证。
