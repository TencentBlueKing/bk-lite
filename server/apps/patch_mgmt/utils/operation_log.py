"""补丁管理操作日志工具。

提供补丁管理操作类别的命名包装函数，统一日志 app='patch'。
每个函数调用 apps.system_mgmt.utils.operation_log_utils.log_operation，
失败时静默（log_operation 内部已捕获异常，不影响主业务流程）。

操作类别：
  补丁生命周期：create / update / delete patch
  目标生命周期：create / update / delete target
  扫描生命周期：scan task create / cancel
  安装生命周期：install task create / cancel
  重启动作：reboot triggered
  补丁源设置（附加）：source changed
  Windows 版本配置（附加）：windows version changed

视图层在完成对应写操作后调用这些函数即可写入操作日志。
"""

from apps.system_mgmt.utils.operation_log_utils import log_operation

_APP = "patch"


# ── 补丁生命周期 ──────────────────────────────────────────────────────────────


def log_patch_created(request, patch_name: str):
    """新增补丁记录。"""
    log_operation(request, "create", _APP, f"新增补丁: {patch_name}")


def log_patch_updated(request, patch_name: str):
    """更新补丁记录。"""
    log_operation(request, "update", _APP, f"更新补丁: {patch_name}")


def log_patch_deleted(request, patch_name: str):
    """删除补丁记录。"""
    log_operation(request, "delete", _APP, f"删除补丁: {patch_name}")


# ── 目标生命周期 ──────────────────────────────────────────────────────────────


def log_target_created(request, target_name: str):
    """新增补丁管理目标。"""
    log_operation(request, "create", _APP, f"新增目标: {target_name}")


def log_target_updated(request, target_name: str):
    """更新补丁管理目标。"""
    log_operation(request, "update", _APP, f"更新目标: {target_name}")


def log_target_deleted(request, target_name: str):
    """删除补丁管理目标。"""
    log_operation(request, "delete", _APP, f"删除目标: {target_name}")


# ── 扫描生命周期 ──────────────────────────────────────────────────────────────


def log_scan_task_created(request, task_name: str):
    """创建补丁扫描任务。"""
    log_operation(request, "execute", _APP, f"创建扫描任务: {task_name}")


def log_scan_task_cancelled(request, task_name: str):
    """取消补丁扫描任务。"""
    log_operation(request, "execute", _APP, f"取消扫描任务: {task_name}")


def log_scan_task_deleted(request, task_name: str):
    """删除补丁扫描任务。"""
    log_operation(request, "delete", _APP, f"删除扫描任务: {task_name}")


# ── 安装生命周期 ──────────────────────────────────────────────────────────────


def log_install_task_created(request, task_name: str):
    """创建补丁安装任务。"""
    log_operation(request, "execute", _APP, f"创建安装任务: {task_name}")


def log_install_task_cancelled(request, task_name: str):
    """取消补丁安装任务。"""
    log_operation(request, "execute", _APP, f"取消安装任务: {task_name}")


def log_governance_task_cancelled(request, task_name: str, reason: str):
    """取消补丁治理任务，并记录用户填写的原因。"""
    log_operation(request, "execute", _APP, f"取消治理任务: {task_name}；原因: {reason}")


# ── 重启动作 ──────────────────────────────────────────────────────────────────


def log_reboot_triggered(request, task_name: str):
    """触发目标重启（安装后立即重启或定时重启）。"""
    log_operation(request, "execute", _APP, f"触发重启: {task_name}")


# ── 补丁源设置（附加） ────────────────────────────────────────────────────────


def log_source_changed(request, action_type: str, source_name: str):
    """补丁源配置变更（action_type: create / update / delete）。"""
    log_operation(request, action_type, _APP, f"补丁源配置变更: {source_name}")


# ── Windows 版本配置（附加） ──────────────────────────────────────────────────


def log_windows_version_changed(request, action_type: str, version_name: str):
    """Windows 版本映射配置变更（action_type: create / update / delete）。"""
    log_operation(request, action_type, _APP, f"Windows版本配置变更: {version_name}")
