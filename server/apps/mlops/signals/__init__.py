"""
MLOps 应用信号注册

在应用启动时自动导入所有信号处理器
"""

from . import base  # noqa: F401
from . import timeseries_signals  # noqa: F401
from . import anomaly_detection_signals  # noqa: F401
from . import log_clustering_signals  # noqa: F401
from . import classification_signals  # noqa: F401
from . import image_classification_signals  # noqa: F401
from . import object_detection_signals  # noqa: F401
