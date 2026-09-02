"""
Default configuration schema for log clustering training.

This module defines supported options and validation rules.
Configuration values should be stored in external JSON files.
"""

from typing import List

from ..evaluation_contract import UNSUPERVISED_METRICS

# Supported model types
SUPPORTED_MODELS: List[str] = [
    "Spell",
    # Future extensions: "Drain", "Logram"
]


# Supported optimization metrics
SUPPORTED_METRICS: List[str] = list(UNSUPERVISED_METRICS)
