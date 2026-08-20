# 配置写范围签名运维说明

Log、Monitor 通过内部 RPC 更新或删除 NodeMgmt 托管配置时，会使用短时签名绑定来源模块、操作类型和完整参数。部署环境可注入以下变量；按仓库安全约定，不修改通用 `.env.example`。

| 变量 | 默认值 | 约束 |
| --- | --- | --- |
| `NODE_CONFIG_WRITE_SIGNING_KEY` | `SECRET_KEY` | 所有签发与验签 Server 副本必须一致，不得写入仓库或日志 |
| `NODE_CONFIG_WRITE_SIGNING_KEY_FALLBACKS` | `[]` | 专用密钥轮换时可验签的旧密钥 JSON 列表 |
| `NODE_CONFIG_WRITE_SCOPE_MAX_AGE_SECONDS` | `60` | 最小 1 秒，代码硬上限 300 秒；非法值回退到 60 秒 |
| `NODE_CONFIG_WRITE_SCOPE_SIGNING_ENABLED` | `false` | 调用方改用 scoped subject；接收端就绪后再开启 |
| `NODE_CONFIG_WRITE_SCOPE_ENFORCEMENT_ENABLED` | `false` | 旧 subject 拒绝可识别的托管配置；所有调用方迁移后再开启 |

## 发布与回滚

1. 首次发布保持两个开关为 `false`，先让新旧副本继续使用旧 subject；可以不设置专用密钥，兼容使用各副本已有且一致的 `SECRET_KEY`。
2. 全部接收端具备 scoped handler 后开启 `NODE_CONFIG_WRITE_SCOPE_SIGNING_ENABLED`，确认 Log/Monitor 正常写删；模块化 NodeMgmt 未安装 owner app 时，签名请求仅在已安装 owner 模型均未声明该 ID 时兼容放行。
3. 旧调用观测清零后再开启 `NODE_CONFIG_WRITE_SCOPE_ENFORCEMENT_ENABLED`。回滚时按相反顺序关闭 enforcement、再关闭 signing，避免新旧版本互相拒绝。
4. 轮换专用密钥时，先在保持旧主密钥的同时把新密钥加入 `NODE_CONFIG_WRITE_SIGNING_KEY_FALLBACKS` 并发布到所有副本；再滚动切换为新主密钥+旧密钥 fallback；预留最长 300 秒后移除旧密钥。
5. 轮换或灰度后核对配置更新/删除失败率；若异常，恢复上一密钥和上一开关阶段，不无界重试。

签名密钥只缩小内部误用面，不替代 NATS 凭据、subject ACL 或用户权限校验。
