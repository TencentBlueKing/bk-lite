# SNMP Trap 采集插件

## 概述

此插件预装在代理节点上，用于采集云区域内网络设备的 SNMP Trap 消息。

## 架构

```
网络设备 (UDP 162) → snmptrapd → Unix Socket → Vector → NATS
```

**关键优势**：
- 使用 **Unix Domain Socket** 进行同主机进程间通信
- 比 UDP 更高效、更可靠、无端口占用
- `logger` 命令原生支持 Unix socket（`-u` 参数）

## 插件文件

1. **snmptrapd.conf** - snmptrapd 配置文件（部署到 `/etc/snmp/snmptrapd.conf`）
2. **vector_trap.toml** - Vector 配置文件（部署到 `/etc/vector/vector_trap.toml`）
3. **collect_type.json** - 插件元数据

## 工作原理

1. **网络设备** 发送 SNMP Trap 到代理节点 UDP 162
2. **snmptrapd** 接收 trap，通过 `traphandle` 调用 `logger` 命令
3. **logger** 将 trap 数据通过 Unix socket 发送到 `/var/run/vector/snmp_trap.sock`
4. **Vector socket source** 监听 Unix socket 并接收数据
5. **Vector transform** 解析 trap 信息（OID、源 IP、类型）
6. **Vector sink** 发送到 NATS 和本地日志

## 节点部署（由安装器负责）

### 1. 安装依赖
```bash
apt-get install -y snmptrapd util-linux
```

### 2. 创建 Socket 目录
```bash
mkdir -p /var/run/vector
chown vector:vector /var/run/vector
chmod 755 /var/run/vector
```

### 3. 部署配置文件
```bash
cp snmptrapd.conf /etc/snmp/snmptrapd.conf
cp vector_trap.toml /etc/vector/vector_trap.toml
```

### 4. 配置 Vector
```bash
# 在 Vector 主配置中导入
echo 'import_config_files = ["/etc/vector/vector_trap.toml"]' >> /etc/vector/vector.toml
```

### 5. 创建 systemd 服务
```bash
cat > /etc/systemd/system/snmptrapd.service << 'EOF'
[Unit]
Description=SNMP Trap Daemon
After=network.target vector.service

[Service]
Type=simple
User=root
ExecStart=/usr/sbin/snmptrapd -f -Lo -C -c /etc/snmp/snmptrapd.conf
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF
```

### 6. 启动服务
```bash
systemctl daemon-reload
systemctl enable --now snmptrapd
systemctl restart vector
```

## 验证

```bash
# 检查 snmptrapd 状态
systemctl status snmptrapd
netstat -ulnp | grep 162

# 检查 Vector Unix socket
ls -l /var/run/vector/snmp_trap.sock

# 发送测试 trap
snmptrap -v 2c -c public 127.0.0.1 '' 1.3.6.1.6.3.1.1.5.3

# 查看日志
journalctl -u snmptrapd -f
tail -f /var/log/snmp_traps/trap_*.log
```

## 为什么选择 Unix Socket？

### 性能对比（同主机通信）

| 方式 | 延迟 | CPU 开销 | 可靠性 |
|------|------|----------|--------|
| **Unix Socket** | **最低** ⭐ | **最低** ⭐ | **最高** ⭐ |
| UDP localhost | 中等 | 中等 | 中等（可能丢包） |
| TCP localhost | 较高 | 较高 | 高（有重传） |

### Unix Socket 优势

1. **零网络栈开销**
   - 数据直接在内核内存中传递
   - 无需经过网络协议栈（TCP/IP）
   - 无校验和计算、路由查找等开销

2. **无端口占用**
   - 使用文件系统路径（`/var/run/vector/snmp_trap.sock`）
   - 避免端口冲突（514 是标准 syslog 端口）
   - 更灵活的权限控制

3. **更可靠**
   - 基于文件系统，不会因网络配置变化而失效
   - 无 UDP 丢包问题
   - 支持流量控制和背压

4. **logger 原生支持**
   ```bash
   logger -u /path/to/socket  # Unix socket
   logger -n host -P port -d  # UDP
   ```

## 网络设备配置

将网络设备的 trap 目标指向代理节点：

**Cisco**:
```
snmp-server host <代理节点IP> version 2c public
snmp-server enable traps
```

**Huawei**:
```
snmp-agent target-host trap address udp-domain <代理节点IP> params securityname public
snmp-agent trap enable
```

## 数据格式

Vector 输出到 NATS 的数据：

```json
{
  "collector": "Snmptrapd",
  "collect_type": "snmp_trap",
  "event_type": "snmp_trap",
  "source_ip": "192.168.1.100",
  "source": "192.168.1.100",
  "trap_oid": "1.3.6.1.6.3.1.1.5.3",
  "trap_type": "linkDown",
  "severity": "warning",
  "timestamp": "2025-11-17T10:30:45Z",
  "raw_message": "原始 trap 消息"
}
```

## 故障排查

### snmptrapd 无法启动
```bash
# 检查配置语法
snmptrapd -f -Lo -d -C -c /etc/snmp/snmptrapd.conf

# 检查 logger 命令
which logger
logger --version
```

### Vector socket 文件不存在
```bash
# 创建目录
mkdir -p /var/run/vector
chown vector:vector /var/run/vector

# 重启 Vector（会自动创建 socket 文件）
systemctl restart vector

# 检查权限
ls -l /var/run/vector/
```

### 无法写入 socket
```bash
# 检查 socket 权限
ls -l /var/run/vector/snmp_trap.sock

# 测试 logger 写入
echo "test" | logger -u /var/run/vector/snmp_trap.sock

# 查看 Vector 日志
journalctl -u vector -f
```

### 收不到 trap
```bash
# 检查防火墙
firewall-cmd --add-port=162/udp --permanent
firewall-cmd --reload

# 手动测试
snmptrap -v 2c -c public 127.0.0.1 '' 1.3.6.1.6.3.1.1.5.3

# 查看 snmptrapd 日志
journalctl -u snmptrapd -f
```

## 技术对比

### UDP localhost vs Unix Socket

**UDP localhost（之前的方案）**:
```
snmptrapd → logger -n 127.0.0.1 -P 514 -d → 网络栈 → Vector UDP:514
           ↓
    占用端口、经过网络协议栈、可能丢包
```

**Unix Socket（推荐方案）**:
```
snmptrapd → logger -u /var/run/vector/snmp_trap.sock → 内核内存 → Vector
           ↓
    无端口、零网络开销、可靠传输
```

3. Vector 的 socket source 接收 UDP 数据包
4. Vector 解析并转发到 NATS
