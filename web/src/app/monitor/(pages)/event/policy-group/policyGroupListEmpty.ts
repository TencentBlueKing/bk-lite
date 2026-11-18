export const POLICY_GROUP_LIST_EMPTY =
  '当前组织还没有这个对象的策略组。接入这个对象的实例时，会自动生成默认策略组；也可以从策略模板新建。';

export function policyGroupListEmptyText(input: { objectSelected: boolean; search: string }): string | null {
  if (!input.objectSelected || input.search.trim()) return null;
  return POLICY_GROUP_LIST_EMPTY;
}
