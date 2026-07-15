# CMDB 全功能审查复现命令附录

> 所有命令均为单条可复制命令；每节明确 cwd、source、env、exit 与关键输出。未记录的历史 ambient 环境明确标为 unknown，不以当前环境反推历史事实。

## 1. 模型治理

- cwd: `/Users/windyzhao/Documents/Canway/weops_X/cmdb/bk-lite/.worktrees/cmdb-functional-production-review/server`
- source: 当前审查 worktree commit
- env: 命令内完整声明

```bash
SECRET_KEY=test DB_ENGINE=sqlite DB_NAME=/private/tmp/cmdb_task2_review.sqlite3 ENABLE_CELERY=true INSTALL_APPS=system_mgmt,node_mgmt,cmdb MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=test MINIO_USE_HTTPS=false uv run pytest -q -o addopts='' apps/cmdb/tests/test_classification_service.py apps/cmdb/tests/test_model_service_advanced.py apps/cmdb/tests/test_unique_rule_crud.py apps/cmdb/tests/test_auto_relation_rule_validate.py apps/cmdb/tests/test_field_group_service.py apps/cmdb/tests/test_public_enum_service.py
```

- exit: 0
- output: `102 passed in 2.83s`

```bash
SECRET_KEY=test DB_ENGINE=sqlite DB_NAME=/private/tmp/cmdb_task2_review.sqlite3 ENABLE_CELERY=true INSTALL_APPS=system_mgmt,node_mgmt,cmdb MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=test MINIO_USE_HTTPS=false uv run pytest -q -o addopts='' apps/cmdb/tests/test_model_views.py::test_model_attr_delete_ok
```

- exit: 1
- output: `1 failed in 2.26s`；`NotSupportedError: contains lookup is not supported on this database backend`
- 历史默认 PostgreSQL 尝试：command/env 未完整留档，不作为可复现证据。

## 2. Stargazer 边界与直接探针

- cwd: `/Users/windyzhao/Documents/Canway/weops_X/cmdb/bk-lite/.worktrees/cmdb-functional-production-review/agents/stargazer`
- source: 当前审查 worktree commit
- env: 历史 ambient env unknown

```bash
make lint
```

- exit: 2
- output: 无 `.pre-commit-config.yaml`

```bash
uv run pytest -q tests/test_collect_multicred.py tests/test_collect_credential_push.py tests/test_ip_discovery_targets.py tests/collect_fixtures/
```

- exit: 2
- output: 收集期 `ModuleNotFoundError: plugins.inputs.ip_discovery`

```bash
uv run pytest -q tests/test_collect_multicred.py tests/test_collect_credential_push.py
```

- exit: 0
- output: `49 passed`

```bash
uv run pytest -q tests/collect_fixtures/
```

- exit: 1
- output: `154 passed, 6 failed, 1 warning`；catalog 实际 56、测试要求 57

```bash
uv run pytest -q tests/test_network_config_file_info.py
```

- exit: 0
- output: `10 passed`

```bash
uv run pytest -q tests/test_ip_discovery_scanner.py
```

- exit: 2
- output: 收集期 `ModuleNotFoundError: plugins.inputs.ip_discovery`

```bash
.venv/bin/python -m pytest -q tests/test_collect_multicred.py --cov=service.collection_service --cov-report=term-missing
```

- exit: 4
- output: `unrecognized arguments: --cov=service.collection_service --cov-report=term-missing`

F26 命令策略：

```bash
.venv/bin/python -c "from plugins.inputs.network_config_file.network_config_file_info import validate_safe_command; print(validate_safe_command('request system reboot'))"
```

- exit: 0
- output: `request system reboot`

F27 空命令：

```bash
.venv/bin/python -c "import plugins.inputs.network_config_file.network_config_file_info as m; F=type('F',(),{'__init__':lambda s,**k:None,'__enter__':lambda s:s,'__exit__':lambda s,*a:None,'disable_paging':lambda s,**k:None}); m.ConnectHandler=F; p={'device_type':'cisco_ios','host':'127.0.0.1','username':'u','password':'p','commands':'','config_name':'running'}; r=m.NetworkConfigFileInfo(p).list_all_resources(); print(r['success'], r['result']['size'], repr(r['result']['content_base64']))"
```

- exit: 0
- output: `True 0 ''`

F29 PowerShell 路径转义：

```bash
.venv/bin/python -c "from plugins.inputs.config_file.config_file_info import ConfigFileInfo; print(ConfigFileInfo._escape_script_value(r\"C:\\ops\\o'Brien.conf\"))"
```

- exit: 0
- output: `C:\ops\o'"'"'Brien.conf`

F31 unknown publish 状态：

```bash
NATS_METRICS_PUBLISH_RETRIES=0 .venv/bin/python -c "import asyncio; from unittest.mock import AsyncMock; import tasks.utils.nats_helper as m; m.nats_publish_lines=AsyncMock(side_effect=RuntimeError('boom')); ns={}; exec('async def main():\n try:\n  await m._publish_lines_with_retry(\"s\", [\"m v=1\"], \"t\")\n except m.MetricsPublishError as e:\n  print(e.success_count, e.delivery_detected, e.attempts)\n', globals(), ns); asyncio.run(ns['main']())"
```

- exit: 0
- output: `0 True 1`；日志含 `publish state unknown` 与 `action=abort_full_batch_retry`

## 3. 专项资源补测

- cwd: `/Users/windyzhao/Documents/Canway/weops_X/cmdb/bk-lite/.worktrees/cmdb-functional-production-review/server`
- source: `6391586c7476dc700cf27d3a205a2e6b5f8a16c2`；新鲜重跑时间 `2026-07-15 12:10 CST`
- env: 命令内完整声明

```bash
MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=test MINIO_USE_HTTPS=false SECRET_KEY=test DB_ENGINE=sqlite DB_NAME=/private/tmp/cmdb-task9-review.sqlite3 ENABLE_CELERY=true INSTALL_APPS=system_mgmt,node_mgmt,cmdb uv run pytest -q -o addopts='' apps/cmdb/tests/test_k8s_resource_overview_service.py apps/cmdb/tests/test_k8s_resource_overview_views.py apps/cmdb/tests/test_application_resource_overview_views.py apps/cmdb/tests/test_infra_service.py apps/cmdb/tests/test_rack_room_service.py --cov=apps.cmdb.services.k8s_resource_overview --cov=apps.cmdb.services.application_resource_overview --cov=apps.cmdb.services.infra --cov=apps.cmdb.services.rack_room --cov=apps.cmdb.views.k8s_setup --cov-report=term-missing
```

- sandbox exit: 101；macOS `system-configuration` panic，未收集
- approved rerun exit: 0
- output: `51 passed in 5.26s`；合计 coverage 63%

```bash
MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=test MINIO_USE_HTTPS=false SECRET_KEY=test DB_ENGINE=sqlite DB_NAME=/private/tmp/cmdb-task9-review.sqlite3 ENABLE_CELERY=true INSTALL_APPS=system_mgmt,node_mgmt,cmdb uv run pytest -q -o addopts='' apps/cmdb/tests/test_k8s_setup_views.py --cov=apps.cmdb.views.k8s_setup --cov=apps.cmdb.services.k8s_setup --cov-report=term-missing
```

- exit: 0
- output: `6 passed in 0.16s`；View 79%、Service 34%、合计 54%

## 4. Enterprise collect

### 4.1 Server

- cwd: `/Users/windyzhao/Documents/Canway/weops_X/cmdb/bk-lite/server`
- source: ignored Overlay aggregate `9b82d0556665cc80c03a44c2b58e10e77ddc005fdc11aad6fcd27713ce139292`
- env: 命令内完整声明

```bash
MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=test MINIO_USE_HTTPS=false SECRET_KEY=test DB_ENGINE=sqlite DB_NAME=/private/tmp/cmdb-enterprise-collect-audit.sqlite3 ENABLE_CELERY=true INSTALL_APPS=system_mgmt,node_mgmt,cmdb,cmdb_enterprise UV_CACHE_DIR=/private/tmp/uv-cache uv run pytest -q -o addopts='' --cov=apps.cmdb_enterprise.collect --cov=apps.cmdb.collection.plugins --cov=apps.cmdb.node_configs --cov=apps.cmdb.collect.extensions --cov=apps.cmdb.services.collect_object_tree --cov-report=term-missing apps/cmdb_enterprise/tests/test_dameng_collect_chain_pure.py apps/cmdb_enterprise/tests/test_dameng_node_params_service.py apps/cmdb_enterprise/tests/test_new_collect_objects_enterprise_boundary.py apps/cmdb_enterprise/tests/test_new_collect_objects_formatters.py apps/cmdb_enterprise/tests/test_new_collect_objects_pipeline.py apps/cmdb/tests/test_enterprise_extensions.py apps/cmdb/tests/test_extensions_registry.py apps/cmdb/tests/test_new_collect_objects_model_config.py
```

- sandbox exit: 101；uv 在 macOS system-configuration 沙箱中 panic，未收集
- approved rerun exit: 1
- output: `26 passed, 1 failed in 5.69s`；失败测试要求树中存在已显式合并到 host 的 `aix`
- coverage: 总计 66%（2062 statements / 701 missed）；Enterprise collect 约 72%（491 / 137）

### 4.2 Stargazer Enterprise plugins

- cwd: `/Users/windyzhao/Documents/Canway/weops_X/cmdb/bk-lite/agents/stargazer`
- source: ignored runtime aggregate `f580f0905b5fc9b84b71628b26b1ed6ad33733ce439babd2a38ccad38c67cf53`

```bash
.venv/bin/python -m pytest -q -o addopts='' tests/test_new_collect_objects_plugins.py tests/test_remaining_collect_objects_plugins.py
```

- exit: 0
- output: `9 passed, 1 warning in 0.36s`

```bash
.venv/bin/python -m pytest -q -o addopts='' --cov=enterprise.plugins.inputs --cov=core.plugin_executor --cov=core.yaml_reader --cov-report=term-missing tests/test_new_collect_objects_plugins.py tests/test_remaining_collect_objects_plugins.py
```

- exit: 4
- output: pytest 未识别 `--cov` 参数，当前 venv 未安装 pytest-cov

### 4.3 F65–F69 直接探针

只读 fixture：

- [enterprise_server_probes.py](reproductions/enterprise_server_probes.py)
- [enterprise_stargazer_probes.py](reproductions/enterprise_stargazer_probes.py)

#### F65 credential schema

- cwd: `/Users/windyzhao/Documents/Canway/weops_X/cmdb/bk-lite/server`
- env: `PYTHONPATH=. DJANGO_SETTINGS_MODULE=settings MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=test MINIO_USE_HTTPS=false SECRET_KEY=test DB_ENGINE=sqlite DB_NAME=/private/tmp/cmdb-enterprise-probes.sqlite3 ENABLE_CELERY=true INSTALL_APPS=system_mgmt,node_mgmt,cmdb,cmdb_enterprise UV_CACHE_DIR=/private/tmp/uv-cache`

```bash
PYTHONPATH=. DJANGO_SETTINGS_MODULE=settings MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=test MINIO_USE_HTTPS=false SECRET_KEY=test DB_ENGINE=sqlite DB_NAME=/private/tmp/cmdb-enterprise-probes.sqlite3 ENABLE_CELERY=true INSTALL_APPS=system_mgmt,node_mgmt,cmdb,cmdb_enterprise UV_CACHE_DIR=/private/tmp/uv-cache .venv/bin/python /Users/windyzhao/Documents/Canway/weops_X/cmdb/bk-lite/.worktrees/cmdb-functional-production-review/docs/reviews/cmdb-functional-review-2026-07-14/reproductions/enterprise_server_probes.py f65
```

- exit: 0
- output: `{'objects': 49, 'encrypted_fields': ['password'], 'accepted_secret_fields': ['access_key', 'community', 'secret_key', 'token']}`

#### F66 无 I/O success

- cwd: `/Users/windyzhao/Documents/Canway/weops_X/cmdb/bk-lite/agents/stargazer`
- env: `PYTHONPATH=.`

```bash
PYTHONPATH=. .venv/bin/python /Users/windyzhao/Documents/Canway/weops_X/cmdb/bk-lite/.worktrees/cmdb-functional-production-review/docs/reviews/cmdb-functional-review-2026-07-14/reproductions/enterprise_stargazer_probes.py f66
```

- exit: 0
- output: `{'result': {'xsky': [{'ip_addr': '203.0.113.254', 'port': 443, 'name': 'xsky', 'version': '', 'status': '', 'vendor': '', 'model': '', 'serial_number': '', 'description': ''}]}, 'success': True}`

#### F67 IBM MQ 路由

- cwd: `/Users/windyzhao/Documents/Canway/weops_X/cmdb/bk-lite/agents/stargazer`
- env: `PYTHONPATH=.`

```bash
PYTHONPATH=. .venv/bin/python /Users/windyzhao/Documents/Canway/weops_X/cmdb/bk-lite/.worktrees/cmdb-functional-production-review/docs/reviews/cmdb-functional-review-2026-07-14/reproductions/enterprise_stargazer_probes.py f67
```

- exit: 0
- output: `['ibmmq_info', 'ibmmq_info']`

首次错误断言完整复现：

```bash
PYTHONPATH=. .venv/bin/python /Users/windyzhao/Documents/Canway/weops_X/cmdb/bk-lite/.worktrees/cmdb-functional-production-review/docs/reviews/cmdb-functional-review-2026-07-14/reproductions/enterprise_stargazer_probes.py f67_expected_gauge_failure
```

- exit: 1
- output: `AssertionError: ['ibmmq_info', 'ibmmq_info']`，断言期望 `ibmmq_info_gauge/ibmmq_channel_info_gauge`；修正命令即上方 F67。

#### F68 stale→fresh

- cwd: `/Users/windyzhao/Documents/Canway/weops_X/cmdb/bk-lite/server`
- env: `PYTHONPATH=. DJANGO_SETTINGS_MODULE=settings MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=test MINIO_USE_HTTPS=false SECRET_KEY=test DB_ENGINE=sqlite DB_NAME=/private/tmp/cmdb-enterprise-probes.sqlite3 ENABLE_CELERY=true INSTALL_APPS=system_mgmt,node_mgmt,cmdb,cmdb_enterprise UV_CACHE_DIR=/private/tmp/uv-cache`

```bash
PYTHONPATH=. DJANGO_SETTINGS_MODULE=settings MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=test MINIO_USE_HTTPS=false SECRET_KEY=test DB_ENGINE=sqlite DB_NAME=/private/tmp/cmdb-enterprise-probes.sqlite3 ENABLE_CELERY=true INSTALL_APPS=system_mgmt,node_mgmt,cmdb,cmdb_enterprise UV_CACHE_DIR=/private/tmp/uv-cache .venv/bin/python /Users/windyzhao/Documents/Canway/weops_X/cmdb/bk-lite/.worktrees/cmdb-functional-production-review/docs/reviews/cmdb-functional-review-2026-07-14/reproductions/enterprise_server_probes.py f68
```

- exit: 0
- output: `{'nacos': [], 'nacos_node': [], 'nacos_namespace': [], 'nacos_service': []}`

#### F69 fallback

- cwd: `/Users/windyzhao/Documents/Canway/weops_X/cmdb/bk-lite/agents/stargazer`
- env: `PYTHONPATH=.`

首次 Nacos fallback 候选 import：

```bash
PYTHONPATH=. .venv/bin/python -c 'import plugins.inputs.nacos.nacos_info; print("loaded")'
```

- exit: 1
- output: `ModuleNotFoundError: No module named 'requests'`

修正为无额外依赖的 SSHPlugin fallback 控制流：

```bash
PYTHONPATH=. .venv/bin/python /Users/windyzhao/Documents/Canway/weops_X/cmdb/bk-lite/.worktrees/cmdb-functional-production-review/docs/reviews/cmdb-functional-review-2026-07-14/reproductions/enterprise_stargazer_probes.py f69
```

- exit: 0
- output: `Plugin fallback triggered: model_id=dameng, failed_source=enterprise, fallback_source=oss`；`plugins.script_executor.SSHPlugin`


## 5. Enterprise 附件、模型与实例扩展

- cwd: `/Users/windyzhao/Documents/Canway/weops_X/cmdb/bk-lite/server`
- source: ignored Overlay aggregate `9b82d0556665cc80c03a44c2b58e10e77ddc005fdc11aad6fcd27713ce139292`
- env: `MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=test MINIO_USE_HTTPS=false INSTALL_APPS=system_mgmt,node_mgmt,cmdb,cmdb_enterprise`

```bash
MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=test MINIO_USE_HTTPS=false INSTALL_APPS=system_mgmt,node_mgmt,cmdb,cmdb_enterprise uv run pytest -q -o addopts='' apps/cmdb_enterprise/tests/test_file_field_service.py apps/cmdb_enterprise/tests/test_file_field_integration.py apps/cmdb_enterprise/tests/test_attachment_view_integration.py apps/cmdb_enterprise/tests/test_fulltext_exclude_file_fields.py --cov=apps.cmdb_enterprise.instance_ops --cov=apps.cmdb_enterprise.model_ops --cov=apps.cmdb_enterprise.models.file_object --cov-report=term-missing
```

- sandbox exit: 2；uv cache 无权读取，未收集
- approved rerun exit: 0
- output: `21 passed in 30.42s`
- coverage: `instance_ops/service.py` 80%、`storage.py` 41%、`tasks.py` 0%、`model_ops/provider.py` 89%、`file_object.py` 97%，合计 72%

```bash
MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=test MINIO_USE_HTTPS=false INSTALL_APPS=system_mgmt,node_mgmt,cmdb,cmdb_enterprise uv run pytest -q -o addopts='' apps/cmdb/tests/test_instance_service_crud.py apps/cmdb/tests/bdd/test_instance_crud_bdd.py
```

- exit: 0
- output: `37 passed in 26.10s`

```bash
MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=test MINIO_USE_HTTPS=false INSTALL_APPS=system_mgmt,node_mgmt,cmdb,cmdb_enterprise uv run python manage.py makemigrations cmdb_enterprise --check --dry-run
```

- exit: 0
- output: `No changes detected in app 'cmdb_enterprise'`

Provider/AppConfig 顺序：

```bash
MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=test MINIO_USE_HTTPS=false INSTALL_APPS=system_mgmt,node_mgmt,cmdb,cmdb_enterprise uv run python -c "import django; django.setup(); from django.apps import apps; from apps.cmdb.extensions.registry import registry; print('enterprise_index=', [c.name for c in apps.get_app_configs()].index('apps.cmdb_enterprise')); print('cmdb_index=', [c.name for c in apps.get_app_configs()].index('apps.cmdb')); print('provider=', type(registry.get('model_ops')).__name__)"
```

- exit: 0
- output: `enterprise_index=20`、`cmdb_index=21`、`provider=FileFieldModelExtension`

## 6. NATS 计数与异常协议

- cwd: `/Users/windyzhao/Documents/Canway/weops_X/cmdb/bk-lite/.worktrees/cmdb-functional-production-review`
- env: none

```bash
rg -c '^@nats_client\.register$' server/apps/cmdb/nats/nats.py
```

- exit: 0
- output: `26`

- cwd: `/Users/windyzhao/Documents/Canway/weops_X/cmdb/bk-lite/.worktrees/cmdb-functional-production-review/server`

```bash
.venv/bin/python -c 'import jsonpickle; e=RuntimeError("password=canary-secret"); print(jsonpickle.encode(e)); print(str(jsonpickle.decode(jsonpickle.encode(e))))'
```

- exit: 0
- output: 编码内容与 decode 后异常文本均包含 `password=canary-secret`

## 7. 文档终验

- cwd: `/Users/windyzhao/Documents/Canway/weops_X/cmdb/bk-lite/.worktrees/cmdb-functional-production-review`
- env: none

Finding 数量、唯一性、严重度、十字段和顺序：

```bash
ruby -e 'files=Dir["docs/reviews/cmdb-functional-review-2026-07-14/{01,02,03,04,05,06,07,08,09,10,11,12,14}-*.md"]; fs=[]; req=["Severity","Location","Root cause category","Evidence","Trigger","Impact","Why existing tests missed it","Minimal safe fix","Required tests","Long-term design note"]; files.each{|f| s=File.read(f); s.scan(/^### Finding CMDB-F(\d+).*?$(.*?)(?=^### |^## |\z)/m){|id,b| sev=b[/^- Severity: (P[0-3])$/,1]; miss=req.reject{|k| b.match?(/^- #{Regexp.escape(k)}:/)}; abort("#{f}:F#{id} missing #{miss.join(",")}") unless miss.empty?; fs << [id.to_i,sev,f]}}; abort("duplicate IDs") unless fs.map(&:first).uniq.size==fs.size; order={"P0"=>0,"P1"=>1,"P2"=>2,"P3"=>3}; files.each{|f| rows=fs.select{|x|x[2]==f}; abort("#{f}: severity order") unless rows.map{|x|order[x[1]]}==rows.map{|x|order[x[1]]}.sort}; counts=fs.group_by{|x|x[1]}.transform_values(&:size); abort("count #{fs.size} #{counts}") unless fs.size==73 && counts=={"P0"=>28,"P1"=>39,"P2"=>6}; puts({findings:fs.size,unique:fs.map(&:first).uniq.size,severity:counts}.inspect)'
```

- expected exit: 0
- expected output: `{:findings=>73, :unique=>73, :severity=>{"P0"=>28, "P1"=>39, "P2"=>6}}`

链接：

```bash
ruby -e 'root="docs/reviews/cmdb-functional-review-2026-07-14"; bad=[]; Dir["#{root}/*.md"].each{|f| File.read(f).scan(/\[[^\]]+\]\(([^)#]+\.md)(?:#[^)]+)?\)/){|m| p=File.expand_path(m[0],File.dirname(f)); bad << [f,m[0]] unless File.file?(p)}}; abort(bad.inspect) unless bad.empty?; puts "markdown_links=ok"'
```

占位符：

```bash
pattern='待''补充|TB''D|TO''DO|待''定|待''确认'; rg -n "$pattern" docs/reviews/cmdb-functional-review-2026-07-14
```

- expected exit: 1
- expected output: none

格式和交付范围：

```bash
git diff --check -- docs/reviews/cmdb-functional-review-2026-07-14
```

```bash
git status --short
```

```bash
git diff --cached --name-only
```

未闭合反引号：

```bash
ruby -e 'Dir["docs/reviews/cmdb-functional-review-2026-07-14/**/*.md"].each{|f| fenced=false; File.readlines(f).each_with_index{|line,i| if line.lstrip.start_with?("```" ); fenced=!fenced; next; end; next if fenced; abort("#{f}:#{i+1}: odd backticks") if line.scan(/\x60/).size.odd?}; abort("#{f}: unclosed fence") if fenced}; puts "backticks=ok"'
```

终验后异常尾部与 EOF：

```bash
ruby -e 'root="docs/reviews/cmdb-functional-review-2026-07-14"; e=File.read("#{root}/evidence-index.md"); tail=e.split("## 最终终验记录\n",2); abort("missing/multiple final section") unless tail.size==2 && !tail[1].include?("\n## "); abort("unexpected evidence tail") unless tail[1].lines.reject{|x|x.strip.empty?}.last&.start_with?("- Enterprise provenance:","- Enterprise provenance："); Dir["#{root}/**/*.{md,py}"].each{|f| s=File.binread(f); abort("#{f}: EOF") unless s.end_with?("\n") && !s.end_with?("\n\n")}; puts "tail_and_eof=ok"'
```
