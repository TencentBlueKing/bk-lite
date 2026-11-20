export const POLICY_GROUP_LIST_EMPTY =
  '当前组织还没有这个对象的策略组。接入这个对象的实例时，会自动生成默认策略组；也可以从策略模板新建。';

export const POLICY_GROUP_DEFAULT_REMOVED_EMPTY =
  '当前组织还没有这个对象的策略组。默认组已删除，之后新实例不再自动告警。可以从策略模板新建。';

export function appliedPolicyGroupSearch(value: string | undefined): string {
  return (value ?? '').trim();
}

export function policyGroupListEmptyText(input: {
  objectSelected: boolean;
  search: string;
  defaultRemoved?: boolean;
}): string | null {
  if (!input.objectSelected || input.search.trim()) return null;
  if (input.defaultRemoved) return POLICY_GROUP_DEFAULT_REMOVED_EMPTY;
  return POLICY_GROUP_LIST_EMPTY;
}
