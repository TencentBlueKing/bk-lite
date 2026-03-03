from typing import List, Optional
from enum import Enum


class DimensionType(str, Enum):
    APPLICATION = "application_first"
    INFRASTRUCTURE = "infrastructure_first"
    INSTANCE = "instance_first"
    CUSTOM = "custom"


class DimensionResolver:
    PRESET_DIMENSION_MAP = {
        DimensionType.APPLICATION: ["service"],
        DimensionType.INFRASTRUCTURE: ["location"],
        DimensionType.INSTANCE: ["resource_name"],
    }

    FALLBACK_ORDER = [
        DimensionType.APPLICATION,
        DimensionType.INFRASTRUCTURE,
        DimensionType.INSTANCE,
    ]

    @classmethod
    def resolve_dimensions_for_strategy(
        cls,
        dimension_type: str,
        custom_dimensions: Optional[List[str]] = None,
    ) -> List[List[str]]:
        if dimension_type == DimensionType.CUSTOM.value or dimension_type == "custom":
            if custom_dimensions:
                return [custom_dimensions]
            return [["event_id"]]

        try:
            dim_type = DimensionType(dimension_type)
        except ValueError:
            dim_type = DimensionType.INSTANCE

        start_index = cls.FALLBACK_ORDER.index(dim_type)
        result = []

        for fallback_type in cls.FALLBACK_ORDER[start_index:]:
            result.append(cls.PRESET_DIMENSION_MAP[fallback_type])

        result.append(["event_id"])
        return result
