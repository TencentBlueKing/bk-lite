import os

from django.conf import settings
from jinja2 import Environment, FileSystemLoader
from typing import List
from apps.alerts.aggregation.window.factory import WindowConfig


class SQLBuilder:
    def __init__(self):
        template_dir = os.path.join(settings.BASE_DIR, "apps/alerts/aggregation/templates")
        self.env = Environment(loader=FileSystemLoader(template_dir))

    def build_aggregation_sql(
        self,
        dimensions: List[str],
        window_config: WindowConfig,
        strategy_id: int,
    ) -> str:
        template_name = (
            "session_window.jinja"
            if window_config.is_session_window
            else "sliding_window.jinja"
        )

        template = self.env.get_template(template_name)

        window_start = window_config.get_window_start().isoformat()

        context = {
            "dimensions": dimensions,
            "window_start": window_start,
            "min_event_count": 1,
            "strategy_id": strategy_id,
        }

        if window_config.is_session_window:
            context["session_end_time"] = (
                window_config.get_session_end_time().isoformat()
            )

        return template.render(context)
