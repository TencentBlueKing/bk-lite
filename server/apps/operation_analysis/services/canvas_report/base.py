from typing import Any, Protocol


class CanvasReportAdapter(Protocol):
    """画布报告订阅适配边界：布局/权限/快照契约，不含编排与投递。"""

    resource_type: str

    def load_resource(self, resource_id: int) -> Any:
        """按主键加载画布实体；不存在时抛出模型 DoesNotExist。"""

    def build_manifest(self, resource: Any) -> list[dict]:
        """从布局收集 {widget_id, widget_type, datasource_id}。"""

    def load_filters(self, resource: Any) -> Any:
        """读取创建/执行所需的筛选定义（深拷贝）。"""

    def build_render_snapshot_fields(self, resource: Any) -> dict:
        """组装 Render Snapshot 展示输入（深拷贝布局/筛选等）。"""

    def render_route_key(self) -> str:
        """Worker/前端渲染路由选择键。"""

    def resource_display_label(self) -> str:
        """投递/邮件使用的画布类型展示标签（冻结进 Snapshot）。"""

    def can_view_resource(
        self,
        user,
        resource: Any,
        *,
        team_id: int,
        include_children: bool = False,
    ) -> bool:
        """画布实例查看权限（不含 DS/Channel 等其他层）。"""

    def terminate_subscriptions_on_delete(
        self,
        resource: Any,
        *,
        actor: str,
        actor_domain: str = "",
    ) -> int:
        """画布销毁前终止关联未删除订阅；返回终止条数。"""
