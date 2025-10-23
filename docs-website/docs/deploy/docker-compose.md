# 系统部署指南（Docker Compose）

本指南帮助你使用 Docker Compose 快速部署 **BK‑Lite**，并根据需要选择是否启用 **OpsPilot AI** 模块。

---

## 1. 环境要求

- Docker >= **20.10.23**
- Docker Compose >= **v2.27.0**
- 推荐：如果需要体验 OpsPilot AI，单机内存 **≥ 8 GB**

---

## 2. 国内镜像加速（可选）

国内环境建议先配置镜像加速：

```bash
export MIRROR=bk-lite.tencentcloudcr.com/bklite
```

> 说明：设置后，安装与打包步骤会优先使用上述镜像源。

---

## 3. 在线安装（快速开始）

### 3.1 完整版（包含 OpsPilot AI）

推荐使用完整版，获得完整 AI 助手能力：

```bash
curl -sSL https://bklite.ai/install.run | bash -s - --opspilot
```

### 3.2 基础版（不含 OpsPilot AI）

如果资源有限或暂不需要 AI 功能：

```bash
curl -sSL https://bklite.ai/install.run | bash -s -
```

> 注：安装脚本支持 **幂等**，重复执行不会破坏已部署环境。

---

## 4. 离线安装

当目标服务器无法访问外网时，先在一台 **可联网** 且满足版本要求的机器上制作离线包，再拷贝到目标服务器进行安装。

### 4.1 制作离线包（联网机器执行）

- 不包含 OpsPilot AI 模块：

```bash
curl -sSL https://bklite.ai/install.run | MIRROR=bk-lite.tencentcloudcr.com/bklite bash -s - package
```

- 包含 OpsPilot AI 模块：

```bash
curl -sSL https://bklite.ai/install.run | MIRROR=bk-lite.tencentcloudcr.com/bklite bash -s - package --opspilot
```

执行完成后，离线安装所需内容会生成在 **/opt/bk-lite** 目录。

### 4.2 打包与分发离线包（联网机器执行）

将生成的 **bklite-offline.tar.gz** 拷贝到目标服务器（离线环境）。

### 4.3 在目标服务器安装（离线机器执行）

```bash
sudo mkdir -p /opt
sudo tar -xzvf bklite-offline.tar.gz -C /opt
cd /opt/bk-lite
export OFFLINE=true
bash bootstrap.sh            # 基础版
# 或
# bash bootstrap.sh --opspilot  # 完整版（含 AI 模块）
```

---

## 5. 卸载

如需完全卸载系统：

```bash
curl -sSL https://bklite.ai/uninstall.sh | bash -s -
```

---

## 常见问题

- **安装可以重复执行吗？** 可以。脚本为幂等设计，重复执行用于修复或更新都安全。
- **没有配置 MIRROR 可以安装吗？** 可以，但在国内网络环境下建议配置以提升下载速度与稳定性。
- **内存不足 8 GB 能否启用 OpsPilot AI？** 不建议，可能出现性能问题或安装失败。