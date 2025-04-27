from django.db.models import Q

from apps.opspilot.models import Bot, FileKnowledge, LLMSkill, QuotaRule, TeamTokenUseInfo


def get_quota_client(request):
    teams = request.user.group_list
    current_team = request.COOKIES.get("current_team")
    if not current_team:
        current_team = teams[0]
    client = QuotaUtils(request.user.username, current_team)
    return client


class QuotaUtils(object):
    def __init__(self, username, team):
        self.username = username
        self.team = team
        self.quota_list = self.get_quota_list()

    def get_quota_list(self):
        quota_list = QuotaRule.objects.filter(
            Q(target_type="user", target_list__contains=self.username)
            | Q(target_type="group", target_list__contains=self.team)
        ).values()
        return list(quota_list)

    def get_file_quota(self):
        unit_map = {"GB": 1024, "MB": 1}
        file_size_map = {"shared": [], "private": []}
        type_map = {"shared": "shared", "uniform": "private"}
        if not self.quota_list:
            return -1, 0, False
        for quota in self.quota_list:
            file_size_map[type_map[quota["rule_type"]]].append(quota["file_size"] * unit_map[quota["unit"]])
        if file_size_map["private"]:
            file_size_list = file_size_map["private"]
            file_list = FileKnowledge.objects.filter(knowledge_document__created_by=self.username)
        else:
            file_size_list = file_size_map["shared"]
            file_list = FileKnowledge.objects.filter(knowledge_document__knowledge_base__team=self.team)
        used_file_size_list = [i.file.size for i in file_list if i.file] + [0]
        used_file_size = sum(used_file_size_list) / 1024 / 1024
        return (
            min(file_size_list) if file_size_list else 0,
            round(used_file_size, 2),
            bool(file_size_map["private"]),
        )

    def get_skill_quota(self):
        skill_count_map = {"shared": [], "private": []}
        type_map = {"shared": "shared", "uniform": "private"}
        if not self.quota_list:
            return -1, 0, False
        for quota in self.quota_list:
            skill_count_map[type_map[quota["rule_type"]]].append(quota["skill_count"])
        if skill_count_map["private"]:
            skill_count_list = skill_count_map["private"]
            skill_count = LLMSkill.objects.filter(created_by=self.username, is_template=False).count()
        else:
            skill_count_list = skill_count_map["shared"]
            skill_count = LLMSkill.objects.filter(team__contains=self.team, is_template=False).count()

        return (
            min(skill_count_list) if skill_count_list else 0,
            skill_count,
            bool(skill_count_map["private"]),
        )

    def get_bot_quota(self):
        bot_count_map = {"shared": [], "private": []}
        type_map = {"shared": "shared", "uniform": "private"}
        if not self.quota_list:
            return -1, 0, False
        for quota in self.quota_list:
            bot_count_map[type_map[quota["rule_type"]]].append(quota["bot_count"])
        if bot_count_map["private"]:
            bot_count_list = bot_count_map["private"]
            bot_count = Bot.objects.filter(created_by=self.username).count()
        else:
            bot_count_list = bot_count_map["shared"]
            bot_count = Bot.objects.filter(team__contains=self.team).count()
        return (
            min(bot_count_list) if bot_count_list else 0,
            bot_count,
            bool(bot_count_map["private"]),
        )

    def get_token_quota(self):
        if not self.quota_list:
            return {}
        llm_model_token_set = {}
        unit_map = {"thousand": 1000, "million": 1000000}
        for quota in self.quota_list:
            token_config = quota["token_set"]
            for llm_model, value in token_config.items():
                llm_model_token_set.setdefault(llm_model, []).append(
                    int(value["value"]) * unit_map.get(value["unit"], 1)
                )
        used_token_map = dict(
            TeamTokenUseInfo.objects.filter(group__contains=self.team).values_list("llm_model", "used_token")
        )
        return_data = {}
        for llm_model, value in llm_model_token_set.items():
            return_data[llm_model] = {
                "used_token": used_token_map.get(llm_model, 0),
                "all_token": min(value) if value else 0,
            }
        return return_data

    @staticmethod
    def get_remaining_token(current_team, llm_model):
        if not current_team:
            return 1
        # 修改查询条件，使用正确的方式查询JSON字段中包含特定键的记录
        quota_list = QuotaRule.objects.filter(target_type="group", target_list__contains=current_team).filter(
            **{f"token_set__{llm_model}__isnull": False}  # 查询token_set中包含llm_model作为key的记录
        )
        if not quota_list:
            return 1
        unit_map = {"thousand": 1000, "million": 1000000}
        llm_model_list = []
        for quota in quota_list:
            token_config = quota["token_set"]
            for llm_model_name, value in token_config.items():
                if llm_model_name == llm_model:
                    llm_model_list.append(int(value["value"]) * unit_map.get(value["unit"], 1))
                    break
        used_token = list(
            TeamTokenUseInfo.objects.filter(group__contains=current_team, llm_model=llm_model).values_list(
                "used_token", flat=True
            )
        )
        used_token = sum(used_token) if used_token else 0
        all_token = min(llm_model_list) if llm_model_list else 0
        return all_token - used_token
