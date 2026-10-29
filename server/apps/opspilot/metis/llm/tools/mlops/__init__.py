"""MLOps 内置工具。

用已绑定的时序预测服务，对监控查询结果或用户贴出的序列做预测。
模型不心算外推，也不自己选择未绑定的服务。

说明：本模块 docstring 仅供 parse_tools_yml 入库与界面展示；
给大模型的调用约束写在各 @tool(description=...) 中，运行时从代码加载。
"""

from apps.opspilot.metis.llm.tools.mlops.predict import mlops_predict_timeseries

CONSTRUCTOR_PARAMS = [
    {
        "name": "serving_ids",
        "type": "string",
        "required": True,
        "description": "已绑定的时序预测服务 ID 列表，现阶段只选一个",
    }
]

__all__ = [
    "CONSTRUCTOR_PARAMS",
    "mlops_predict_timeseries",
]
