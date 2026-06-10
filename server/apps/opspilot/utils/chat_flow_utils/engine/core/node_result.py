"""
节点 I/O 契约 - 类型化的 NodeResult

F031: 此前节点执行结果使用未类型化的 Dict，并在多处以 in-band 的
``{"success": False}`` 表达失败，检查方式不一致。这里定义一个类型化的
``NodeResult`` 数据类（ok/output/error/route）来承载节点执行结果。

重要：``node_result`` 是引擎内部契约，绝不会被流式输出（SSE/AGUI）。为保持
零行为变更，``NodeResult`` 通过 ``to_dict()`` 还原为与历史完全一致的 dict 形态，
并通过 ``from_dict()`` 提供兼容读取入口（compat shim），使得仍以旧 dict 键名
（``success``/``node_id``/``node_type``/``data``/``error``/``execution_time``）
读取的代码继续工作。
"""
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class NodeResult:
    """节点执行结果的类型化契约（引擎内部使用，永不流式输出）。

    Attributes:
        ok: 节点是否执行成功（对应历史 dict 的 ``success`` 键）。
        node_id: 节点 ID。
        node_type: 节点类型。
        output: 节点输出数据（对应历史 dict 的 ``data`` 键）。
        error: 失败时的错误信息（对应历史 dict 的 ``error`` 键）。
        execution_time: 执行耗时（秒）。
        route: 路由相关附加字段（如 ``message``），保留以兼容历史 dict 的额外键。
    """

    ok: bool = True
    node_id: Optional[str] = None
    node_type: Optional[str] = None
    output: Any = None
    error: Optional[str] = None
    execution_time: Optional[float] = None
    route: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """还原为与历史完全一致的 dict 形态（compat shim）。

        仅写入历史上会出现的键，保证下游消费方（如 ``_check_chain_result`` /
        ``_record_execution_result`` / ``_get_next_nodes``）行为不变。
        """
        data: Dict[str, Any] = {"success": self.ok}
        if self.node_id is not None:
            data["node_id"] = self.node_id
        if self.node_type is not None:
            data["node_type"] = self.node_type
        if self.ok:
            if self.output is not None:
                data["data"] = self.output
        else:
            data["error"] = self.error if self.error is not None else "未知错误"
        if self.execution_time is not None:
            data["execution_time"] = self.execution_time
        # 保留任何历史上的附加键（如 message）
        for key, value in self.route.items():
            data.setdefault(key, value)
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "NodeResult":
        """从历史 dict 形态读取（compat shim）。

        ``success`` 缺省视为 True（与历史 ``node_result.get("success", True)``
        的检查语义保持一致）。
        """
        if not isinstance(data, dict):
            return cls(ok=True)
        known = {"success", "node_id", "node_type", "data", "error", "execution_time"}
        route = {k: v for k, v in data.items() if k not in known}
        return cls(
            ok=data.get("success", True),
            node_id=data.get("node_id"),
            node_type=data.get("node_type"),
            output=data.get("data"),
            error=data.get("error"),
            execution_time=data.get("execution_time"),
            route=route,
        )
