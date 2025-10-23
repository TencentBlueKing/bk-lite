import logging

from django.core.management import BaseCommand

from apps.rpc.opspilot import OpsPilot
from apps.rpc.system_mgmt import SystemMgmt

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "初始化Guest角色"

    def handle(self, *args, **options):
        sys_client = SystemMgmt()
        res = sys_client.create_guest_role()
        opspilot_client = OpsPilot()
        provider_res = opspilot_client.get_guest_provider(res["data"]["group_id"])
        if not provider_res["result"]:
            logger.error(f"Failed to create guest provider: {provider_res['message']}")
            return
        llm_model = provider_res["data"]["llm_model"]
        rerank_model = provider_res["data"]["rerank_model"]
        embed_model = provider_res["data"]["embed_model"]
        ocr_model = provider_res["data"]["ocr_model"]
        res = sys_client.create_default_rule(llm_model, ocr_model, embed_model, rerank_model)
        if not res["result"]:
            logger.error(f"Failed to create default rule: {res.get('message', '')}")
        else:
            logger.info("Guest role initialized successfully.")
