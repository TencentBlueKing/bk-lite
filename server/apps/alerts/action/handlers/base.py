from abc import ABC, abstractmethod


class ActionHandler(ABC):
    action_type = ""

    @abstractmethod
    def execute(self, rule, alert, execution) -> None:
        """执行动作并把结果写到 execution（自行 save）。绝不抛到引擎之外。"""
