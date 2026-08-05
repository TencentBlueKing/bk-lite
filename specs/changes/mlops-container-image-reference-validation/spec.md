# MLOps 容器镜像引用边界

## 目标

算法配置写入和 Kubernetes 训练、推理执行使用同一套 OCI/Docker 风格镜像引用契约。
含换行、控制字符、多个 JSON 值或非法引用的输入必须在任何 `kubectl` 资源操作前失败，
避免镜像字段越出 YAML scalar 并注入额外资源。

## 调用方与存量盘点

- 六类 MLOps 场景均通过 `get_image_by_prefix` 读取 `AlgorithmConfig.image`，再调用
  `WebhookClient.train` / `WebhookClient.serve`。
- Kubernetes 运行时最终进入 `agents/webhookd/mlops/kubernetes/train.sh` 或 `serve.sh`；
  Docker 运行时不经过 Kubernetes heredoc，但新写入仍受 Server serializer 约束。
- 仓库内置的 10 条算法配置种子全部符合新契约，并由关联测试逐条在 Python 与 Shell 两端验证。
- 既有数据库记录不自动改写，也没有 schema migration；默认镜像、短名称、registry 端口、
  多级路径、tag、digest、tag+digest 和方括号 IPv6 registry 保持可用。

## 失败与兼容契约

- API 创建或更新非法镜像时返回字段级本地化校验错误；合法旧调用保持原行为。
- 初始化命令遇到非法种子时记录文件和具体原因、计入 `skipped_invalid`，并继续处理其余配置，
  不扩大 `batch_init` 的启动失败面。
- Kubernetes 入口对非法或边界不完整的 `train_image` 返回 `INVALID_TRAIN_IMAGE`，且不得调用 `kubectl`。
- Server 与 webhookd 可独立部署，因此两端各自保留校验实现；同一组兼容/拒绝语料和真实脚本入口测试
  用于防止规则漂移。

## 升级与迁移

1. 升级前通过 Django ORM 读取现有 `AlgorithmConfig`，使用
   `apps.mlops.utils.container_image.is_valid_container_image_reference` 审计镜像字段；禁止 raw SQL。
2. 对审计出的非法记录，先确认实际 registry、path、tag 或 digest，再通过现有算法配置编辑接口改为合法引用。
   该操作可重复执行，不删除记录、不改变关联任务。
3. 未完成迁移的非法记录仍可读取和编辑，但 Kubernetes 训练/推理会在资源操作前明确失败；
   修正镜像后可直接重试，不产生半完成 Kubernetes 资源。
4. 发布时先部署 webhookd 执行边界，再部署 Server 写入校验；这样存量非法记录在混合版本期间也会在
   Kubernetes 资源操作前失败，且新 webhookd 仍能处理旧 Server 传入的合法引用。

## 回滚

代码可整体 revert，无数据库回滚步骤。若分阶段回滚，先回滚 Server、再回滚 webhookd；
已修正为合法格式的 AlgorithmConfig 无需恢复。回滚后应重新运行存量审计，确认没有依赖非法格式的配置。
