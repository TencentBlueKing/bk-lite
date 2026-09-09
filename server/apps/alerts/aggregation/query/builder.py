import os
from typing import List

from django.conf import settings
from jinja2 import FileSystemLoader
from jinja2.defaults import DEFAULT_FILTERS

from apps.alerts.aggregation.window.factory import WindowConfig
from apps.core.utils.safe_template import build_trusted_file_template_env


class SQLBuilder:
    def __init__(self):
        template_dir = os.path.join(settings.BASE_DIR, "apps/alerts/aggregation/templates")
        self.env = build_trusted_file_template_env(
            loader=FileSystemLoader(template_dir),
            extra_filters={"default": DEFAULT_FILTERS["default"]},
        )

    def build_aggregation_sql(
        self,
        dimensions: List[str],
        window_config: WindowConfig,
        strategy_id: int,
    ) -> str:
        template_name = "session_window.jinja" if window_config.is_session_window else "sliding_window.jinja"

        template = self.env.get_template(template_name)

        window_start = window_config.get_window_start().isoformat()

        dimension_specs = [self._dimension_spec(dimension) for dimension in dimensions]
        context = {
            "dimensions": dimension_specs,
            "window_start": window_start,
            "min_event_count": 1,
            "strategy_id": strategy_id,
        }

        if window_config.is_session_window:
            context["session_end_time"] = window_config.get_session_end_time().isoformat()

        return template.render(context)

    @staticmethod
    def _dimension_spec(dimension: str) -> dict:
        if dimension.startswith("enrichment."):
            segments = dimension.split(".")[1:]
            json_path = "$." + ".".join(segments)
            legacy_json_path = f"$.{segments[0]}[0]." + ".".join(segments[1:])
            return {
                "name": dimension,
                "expression": (
                    f"coalesce(json_extract_string(enrichment, '{json_path}'), " f"json_extract_string(enrichment, '{legacy_json_path}'))"
                ),
            }
        return {"name": dimension, "expression": dimension}
