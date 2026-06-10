# 日志采集模板安全沙箱渲染修复方案

## 背景

日志模块创建 Docker 日志接入实例时，接口 `POST /api/v1/log/collect_instances/batch_create/` 返回 500。线上容器日志显示后端在渲染采集模板阶段抛出：

```text
jinja2.exceptions.SecurityError: Undefined is not safely callable
```

堆栈指向 `server/apps/log/support-files/plugins/Vector/docker/docker.child.toml.j2` 第 16 行。该模板使用 `_container_name_contains.split(',')` 处理容器名称过滤条件。

日志模板由 `server/apps/log/utils/plugin_controller.py` 调用 `build_sandboxed_env()` 渲染。底层 `server/apps/core/utils/safe_template.py` 的 `StrictSandboxedEnvironment` 会拒绝 callable 属性和函数调用，这是正确的安全边界。问题不是 sandbox 过严，而是少量日志采集模板仍使用了方法调用语法。

## 结论

采用“只改模板语法，不放宽安全沙箱”的方案。

```text
用户创建日志接入实例
  -> CollectInstanceViewSet.batch_create
  -> CollectTypeService.batch_create_collect_configs
  -> Controller.render_template
  -> StrictSandboxedEnvironment
  -> 模板只能使用白名单 filter，不调用对象方法
```

把已知模板中的 `.split(',')` 调用改为已经注册到日志模板环境中的 `| split(',')` 过滤器。这样保持模板能力不变，同时继续禁止对象方法调用、内省和其他高风险模板行为。

## 范围

本次只覆盖已发现并可复现的 `.split(',')` 模板方法调用。

需要修改的模板：

- `server/apps/log/support-files/plugins/Vector/docker/docker.child.toml.j2`
- `server/apps/log/support-files/plugins/Packetbeat/http/http.child.yaml.j2`
- `server/apps/log/support-files/plugins/Auditbeat/file_integrity/file_integrity.child.yaml.j2`

不修改：

- `server/apps/core/utils/safe_template.py`
- `server/apps/log/utils/plugin_controller.py` 的 sandbox 策略
- 日志接入接口协议
- 前端表单字段
- 节点管理 RPC 逻辑

## 模板改造

`plugin_controller.py` 已经通过 `extra_filters` 注册了 `split` 过滤器：

```python
"split": lambda value, separator=",": str(value).split(separator)
```

模板改造只把方法调用改成 filter 管道。

Docker 日志模板：

```jinja2
{{ _container_name_contains | split(',') | map('trim') | reject('equalto', '') | map('tojson') | join(', ') }}
{{ _container_name_exclude | split(',') | map('trim') | reject('equalto', '') | map('tojson') | join(', ') }}
```

Packetbeat HTTP 模板：

```jinja2
{{ _ports | split(',') | map('trim') | map('int') | list | to_json }}
```

Auditbeat file integrity 模板：

```jinja2
{% for path in _monitor_paths | split(',') | map('trim') | reject('equalto', '') %}
{% for path in _exclude_paths | split(',') | map('trim') | reject('equalto', '') %}
```

## 错误处理

这次不改变接口错误响应结构。

修复后，上述模板在合法输入下不应再触发 `Undefined is not safely callable`。如果未来模板新增了未白名单行为，仍应由 sandbox 拒绝，而不是自动放行。

如果用户传入非法业务值，例如 Packetbeat HTTP 端口不是数字，仍沿用现有校验或模板渲染行为。端口业务校验不属于本方案范围。

## 安全边界

本方案保留当前安全模型：

- 不允许模板调用对象方法。
- 不允许访问私有属性或危险属性链。
- 不恢复 Jinja 默认 globals。
- 不新增宽泛 callable 白名单。
- 只使用日志模板环境中已经明确注册的过滤器。

这样修复的是模板与安全沙箱之间的兼容问题，不削弱 SSTI 防护。

## TDD 测试计划

实现必须按 TDD 执行。

先新增失败测试，确认当前模板会因为 `.split(',')` 在 sandbox 下失败，再改模板让测试通过。

新增 `server/apps/log/tests/test_log_template_sandbox_rendering.py`，真实调用 `Controller({}).render_template()`，避免只测试 mock。

测试用例：

1. Docker 模板开启容器过滤时能渲染 `include_containers = ["nginx", "api"]`。
2. Docker 模板开启容器过滤时能渲染 `exclude_containers = ["vector", "logspout"]`。
3. Packetbeat HTTP 模板传入字符串端口 `80,8080,8000` 时能渲染为 `[80, 8080, 8000]`。
4. Auditbeat file integrity 默认路径字符串能渲染出 `/etc/passwd`、`/etc/shadow`、`/etc/sudoers`。
5. Auditbeat file integrity 传入排除路径字符串时能渲染为独立列表项。

验证命令：

```bash
cd server && uv run pytest apps/log/tests/test_log_template_sandbox_rendering.py
```

实现阶段只运行该目标测试文件，避免扩大门禁耗时。

## 验收标准

- Docker 日志接入实例创建不再因容器过滤模板渲染返回 500。
- 三个已知 `.split(',')` 模板调用全部改为 `| split(',')`。
- 目标测试先失败、后通过，并记录失败原因与通过结果。
- `rg "\.split\(" server/apps/log/support-files/plugins` 不再命中日志采集模板中的 Jinja 表达式方法调用。
- 不改动 sandbox 安全策略。

## 不做的事情

本方案不做日志采集模板全量安全审计。

本方案不统一重写所有模板表达式。

本方案不改接口返回格式或前端交互。

本方案不为 Jinja sandbox 增加字符串方法调用白名单。
