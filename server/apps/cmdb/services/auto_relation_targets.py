"""一次对账内共享的目标快照和精确匹配索引，不跨任务缓存。"""
from itertools import chain

from apps.cmdb.services.auto_relation_rule import AUTO_RELATION_MATCHING_RULE_EXACT, AUTO_RELATION_MATCHING_RULE_IEXACT


class TargetSnapshot:
    def __init__(self, instances):
        self.instances = instances
        self.by_id = {instance["_id"]: instance for instance in instances}
        self._indexes = {}

    def candidates(self, source, rule):
        # 先用一个可索引条件缩小候选集；调用方仍校验全部条件，保留 AND/OR 语义。
        for pair in rule.match_pairs:
            if pair.matching_rule not in {AUTO_RELATION_MATCHING_RULE_EXACT, AUTO_RELATION_MATCHING_RULE_IEXACT}:
                continue
            value = source.get(pair.src_field_id)
            key = self._key(value, pair.matching_rule)
            try:
                hash(key)
            except TypeError:
                continue
            index_id = (pair.dst_field_id, pair.matching_rule)
            if index_id not in self._indexes:
                index, unhashable = {}, []
                for target in self.instances:
                    target_key = self._key(target.get(pair.dst_field_id), pair.matching_rule)
                    try:
                        index.setdefault(target_key, []).append(target)
                    except TypeError:
                        unhashable.append(target)
                self._indexes[index_id] = index, unhashable
            index, unhashable = self._indexes[index_id]
            return chain(index.get(key, ()), unhashable)
        return self.instances

    @staticmethod
    def _key(value, matching_rule):
        if matching_rule == AUTO_RELATION_MATCHING_RULE_IEXACT and value is not None:
            return str(value).strip().lower()
        return value
