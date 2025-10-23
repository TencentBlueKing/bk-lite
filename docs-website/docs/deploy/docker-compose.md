# 系统部署

## 部署要求

* docker >= 20.10.23
* docker-compose >=v2.27.0 

**如要体验OpsPilot AI相关特性，推荐服务器单台内存>8GB**

## 安装部署

### 完整版安装（包含OpsPilot AI模块）

推荐使用完整版安装，体验完整的AI助手功能：

```bash
curl -sSL https://bklite.ai/install.run | bash -s - --opspilot
```

### 基础版安装（不包含OpsPilot AI模块）

如果服务器资源有限或不需要AI功能，可选择基础版安装：

```bash
curl -sSL https://bklite.ai/install.run | bash -
```

> 注：安装脚本是幂等的，多次运行不会对当前部署造成影响

## 卸载

如需完全卸载系统，执行以下命令：

```bash
curl -sSL https://bklite.ai/uninstall.sh | bash -
```

