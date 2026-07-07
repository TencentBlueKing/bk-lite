"""技能执行器包装。

- `PathRewritingBackend`:在 deepagents ``LocalShellBackend`` 之外包一层,
  在 ``execute`` / ``aexecute`` 调用前把命令字符串里以 ``/skills/`` 开头的
  路径替换成物理沙箱路径,解决 deepagents 0.5.x ``virtual_mode`` 不重写
  shell 命令字符串的已知限制。

Phase 0 引入,NATS worker 上线后可废弃。
"""
from __future__ import annotations

from .path_rewriting_backend import (
    PathRewritingBackend,
    rewrite_sandbox_paths,
    rewrite_skill_paths,
)

__all__ = ["PathRewritingBackend", "rewrite_sandbox_paths", "rewrite_skill_paths"]