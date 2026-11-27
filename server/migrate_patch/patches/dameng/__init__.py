# 冻结镜像里的 batch_init.exists() 仍可能发出 LIMIT 1 FOR UPDATE。
# 只在 migrate / batch_init 进程安装编译器兜底，避免常驻进程丢掉 .first() 的行锁。
from migrate_patch.patches.lock_compat import install_select_for_update_limit_compat_for_schema_init

install_select_for_update_limit_compat_for_schema_init()
