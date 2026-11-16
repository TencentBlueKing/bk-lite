# 预置时序模型的内置发布记录

Status: ready

## Problem Statement

OpsPilot 只能从 MLOps 的时序预测发布列表里选择模型。正常发布来自一条训练任务，启停、状态和预测都按容器名 `TimeseriesPredict_Serving_{记录ID}` 处理。预置镜像是另一只容器，部署时用 `MLOPS_PRESET_BASE_URL` 告诉 Server 它的地址，预测路径是 `{MLOPS_PRESET_BASE_URL}/{算法名}/predict`。这只容器对不上现有容器名，所以发布列表和 OpsPilot 都看不到它。

## Solution

只做时序预测。预置镜像里的每只时序算法对应一条内置训练任务和一条内置发布记录，挂在默认组织 `Default`。`MLOPS_PRESET_BASE_URL` 有值时，这两条记录出现在列表里，预测走预置地址。变量没有值时，内置记录不出现。Server 不查看容器状态，也不访问容器的健康检查。

发布列表藏起内置记录的启停和删除，接口同时拒绝。使用示例保留，并且可以发送。配置保留，内置发布只能改组织。训练任务列表藏起训练、详情、编辑、删除。重新训练、编辑、删除由接口拒绝，避免删掉训练任务时把发布记录一起级联删掉。详情接口也拒绝，避免用内置记录去查询 MLflow。训练任务的组织不随发布记录改变。

## User Stories

1. As a OpsPilot 调用方, I want the builtin timeseries model to appear in the existing serving list with a positive serving id, so that I can select and call it the same way as a trained model.
2. As a 发布列表用户, I want a builtin serving row to show the algorithm name and a usage example, so that I can try a prediction without starting a container named after the serving id.
3. As a 发布列表用户, I want start, stop, and delete to be absent on a builtin serving row and rejected by the API, so that those actions cannot target the preset container. Configuration stays, and only the organizations can change.
4. As a 训练任务用户, I want train, detail, edit, and delete to be absent on a builtin training job and rejected by the API, so that the job cannot be changed and its detail view cannot query MLflow.
5. As a 部署管理员, I want a missing Default group or a failed builtin seed to warn and let the server finish starting, so that I can run the seed command again after the group exists.

## Implementation Decisions

- 本次只种子 `GradientBoosting`。增加一只时序算法就是再增加一对记录。发布记录的名称只用于列表展示，预测地址使用训练任务的 `algorithm`。
- 部署是否带有预置容器，只看 `MLOPS_PRESET_BASE_URL` 去空白、去尾部斜杠后是否非空。变量存在时内置记录出现；不存在时从列表和可预测列表中排除。
- 两条记录都带 `is_builtin`。序列化器原样返回，页面不把这个字段画成表单项，调用方不能修改。训练任务的 `dataset_version` 为空，`hyperopt_config` 为空，因此保存时不上传 MinIO。发布记录不写 `container_info.port`，`container_info` 为空对象。
- 第一次写入挂在 `name=Default` 且 `parent_id=0` 的组织上。独立执行种子命令时，这个组织不存在则失败并说明原因。`batch_init` 把这次种子当作非关键步骤：失败时写一条告警，包含稳定事件名、`failed_stage`、`error_type`、异常消息和受控堆栈，标准输出只保留异常类型和重试命令，然后继续启动。种子命令自己不再为同一次失败写日志。补偿是再次执行同一条种子命令。已有记录的组织保持不变；缺发布记录时，新发布记录仍挂 `Default`。不给内置记录加数据库唯一约束；发布形态是单副本 Server，`batch_init` 在拉起工作进程之前只跑一次。
- 发布列表对内置记录隐藏启停、删除，保留使用示例和配置。配置里只有组织可改，提交走原来的编辑接口，请求体只有组织。打开配置时不查询模型版本。试调用在内置记录上可发送，不根据 `container_info.state` 判断服务是否运行。普通发布仍要容器处于运行中才能发送。
- 状态刷新跳过内置发布，不向 webhookd 查询 `TimeseriesPredict_Serving_{记录ID}`。启停、删除、移除容器，以及除组织以外的编辑，都在拼接该容器名之前拒绝。只改组织时不查询 MLflow，也不启停容器。内置发布的组织不必与训练任务相同。
- 训练任务列表对内置记录隐藏训练、详情、编辑、删除。重新训练、编辑、删除，以及运行记录、指标、参数、模型版本和模型下载这些会查询 MLflow 的接口，都返回拒绝，并且不访问 MLflow。训练任务的组织不能通过编辑修改。
- 可预测列表在变量存在时放行没有端口的内置发布，普通发布仍要求端口有值。预测请求体保持 `{"data":[...],"config":{"steps":N}}`。内置发布的地址是 `{MLOPS_PRESET_BASE_URL}/{algorithm}/predict`。算法名为空，或包含 `/`、`\`、`..`、`?`、`#` 时拒绝，并且不发出上游请求。像 `My-Model_1` 这样的单段算法名可以通过。日志和标准输出不记录预置地址。

## Testing Decisions

测试从命令、列表接口、预测入口和发布页试调用这些外部行为观察结果，不把数据库唯一约束或页面内部状态当作断言对象。

- 种子命令：变量不存在时不写记录；变量存在且默认组织在时写下一对记录，重复执行不新增；默认组织缺失时命令失败且不写失败日志，补上组织后再执行能写下一对；已有内置训练任务但没有发布记录时只补发布记录；已有内置训练任务的名称或组织与种子不同时复用该行，不覆盖字段；同名普通训练任务旁边仍新建内置记录。
- `batch_init`：种子命令失败时初始化仍成功，告警模板带独立的异常类型和异常消息，恰好一条受控堆栈成立，异常正文不进入标准输出。
- 发布与训练接口：变量不存在时列表看不到内置记录；存在时可见。内置发布的启停、删除、移除容器返回拒绝，并且不调用 webhookd。只提交组织的编辑可以改发布记录，训练任务的组织不变，名称不变，并且不查询 MLflow。编辑里再带其它字段则拒绝，组织不改变。训练任务的重新训练、编辑、删除，以及运行记录详情返回拒绝，并且不查询 MLflow。可预测列表在变量存在时包含没有端口的内置发布。
- 预测：内置发布把请求发到 `{基址}/{algorithm}/predict`，请求体保持原样。算法名会改变路径时返回拒绝，上游请求不发出。
- 使用示例：内置发布的发送按钮可用，且不出现「服务未运行」；普通发布未运行时按钮禁用并出现这句提示，运行中可以发送。

## Out of Scope

- 时序预测以外的算法类型。
- 把预置容器改成按 `TimeseriesPredict_Serving_{记录ID}` 启停或刷新状态。
- 用卷挂载或本地路径代替 `MLOPS_PRESET_BASE_URL`。
- 为同时跑两次种子增加唯一约束或冲突后重读。
- 修改预置模型的特征窗口，或改写所有时序发布共用的默认试调用示例。默认示例只有三个点，预置模型会在特征提取后得到空结果并返回 `E2002`；这是模型输入长度，不是发布路由。

## Further Notes

页面上的「能力发布」就是这里的发布列表。内置发布保留使用示例和配置，配置只改组织。内置训练任务不提供改组织。
