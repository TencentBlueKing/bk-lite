from apps.opspilot.models import LLMSkill
from apps.opspilot.services.skill_init_json import SKILL_LIST


class ModelProviderInitService:
    def __init__(self, owner):
        self.owner = owner
        self.group_id = self.get_group_id()

    @staticmethod
    def get_group_id():
        return 1

    def init(self):
        LLMSkill.objects.filter(is_template=True).delete()
        skill_list = [LLMSkill(**skill) for skill in SKILL_LIST]
        LLMSkill.objects.bulk_create(skill_list, batch_size=10)
