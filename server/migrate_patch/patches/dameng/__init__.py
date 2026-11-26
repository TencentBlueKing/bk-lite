# 常驻进程按主键重写带 LIMIT 的 select_for_update。编译器去掉 FOR UPDATE 的兜底只给 migrate / batch_init。
from migrate_patch.patches.lock_compat import (
    install_select_for_update_limit_compat_for_schema_init,
    install_select_for_update_window_compat,
)

install_select_for_update_window_compat()
install_select_for_update_limit_compat_for_schema_init()
