"""使用组织（usage_team）不变式工具。

不变式：team ⊆ usage_team（管理组织恒为使用组织子集，且排在前面）。
Bot 与 LLMSkill 共用。
"""


def merge_usage_team(team, usage_team):
    """保证 team ⊆ usage_team：管理组织恒在使用组织内、去重、管理组织在前。"""
    merged = list(team or [])
    for org in usage_team or []:
        if org not in merged:
            merged.append(org)
    return merged
