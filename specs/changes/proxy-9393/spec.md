# 区域 Proxy 安装与升级（9393）

Status: done

- Server 在旧中心配置下沿用旧出包协议，支持 Server 和 webhookd 分批升级。配置专用 Leafnode 后要求完整的 v2 契约，中心 Leafnode 与 Agent 客户端使用独立的端口和认证配置。
- Proxy 通过中心 JetStream 源域镜像安装包。安装专用账号只允许安装进度和包下载所需的操作。保留官方 4223 模板、已有 Compose override 及其本地变量。预检安装目录空间，安装器最多自动保留一份成功升级的旧目录。
- 升级前校验源域和已有 mirror。升级后等待关键容器和 TLS 反代就绪，失败时恢复原目录和 Compose 服务。中心认证切换需与 Proxy 升级协调，回滚依次恢复区域安装凭据与中心配置，再恢复 Proxy。账号补齐必须保存回退记录。
- 在独立 Linux 节点验证安装包下载和回连，在隔离 Kubernetes 验证集群外访问。HA 通过配置和逻辑测试验证。
