"""
Default configuration schema for log clustering training.

This module defines supported options and validation rules.
Configuration values should be stored in external JSON files.
"""

from typing import List

# Supported model types
SUPPORTED_MODELS: List[str] = [
    "Spell",
    # Future extensions: "Drain", "Logram"
]


# Supported optimization metrics
SUPPORTED_METRICS: List[str] = [
    "template_quality_score",
    "coverage_rate",
    "template_diversity",
    "num_templates",
]
