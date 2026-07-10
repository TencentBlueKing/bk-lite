#!/bin/bash
# ibmmq 采集 wrapper 占位（G2.2 选 B — license 不可达）
# -----------------------------------------------------------------------------
# 此文件是 catalog Spec 注册用的占位 init_script,真实采集脚本待 IBM MQ license
# 就位后实施。
#
# 同步策略:IBM MQ license 提供后,按 plugins/inputs/db2/db2_default_discover.sh
# (或同类商业中间件脚本) 的风格,扫 `dspmq` 输出 + `ps` 找 `runmqlsr` 进程,
# 提取 qmgr_name / port / version / install_path 等字段。
#
# 参考:
# - docs/superpowers/plans/2026-07-06-cmdb-collect-v3-roadmap.md §3.4 G2.2
# - docs/superpowers/plans/2026-07-07-cmdb-collect-v3-phase2-plan.md §3.2
# -----------------------------------------------------------------------------
echo '{"inst_name":"placeholder-ibmmq","bk_obj_id":"ibmmq","ip_addr":"127.0.0.1","port":"0","version":"placeholder","install_path":"","java_path":"","java_version":"","xms":"","xmx":""}'