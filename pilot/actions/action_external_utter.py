from typing import Any, Dict, List, Text

from rasa_sdk import Action, Tracker
from rasa_sdk.events import SlotSet
from rasa_sdk.executor import CollectingDispatcher
from utils.rasa_utils import RasaUtils


class ActionExternalUtter(Action):
    def name(self) -> Text:
        return "action_external_utter"

    async def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Dict[Text, Any]]:
        external_utter_content = tracker.get_slot("external_utter_content")
        external_utter_channel = tracker.get_slot("external_utter_channel")

        RasaUtils.log_info(
            tracker,
            f"接收到主动触发回复请求,内容为: {external_utter_content},通信渠道为: {external_utter_channel}",
        )

        # Web通道直接回复,其他通道调用了不会触发事件
        dispatcher.utter_message(external_utter_content)

        return [
            SlotSet("external_utter_content", None),
            SlotSet("external_utter_channel", None),
        ]
