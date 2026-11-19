import { describe, expect, it } from 'vitest';

import { POLICY_GROUP_LIST_EMPTY, policyGroupListEmptyText } from '../policyGroupListEmpty';

describe('策略组列表空状态', () => {
  it('选中对象且没有搜索时说明默认组会在接入时生成', () => {
    expect(policyGroupListEmptyText({ objectSelected: true, search: '' })).toBe(POLICY_GROUP_LIST_EMPTY);
    expect(policyGroupListEmptyText({ objectSelected: true, search: '  ' })).toBe(POLICY_GROUP_LIST_EMPTY);
  });

  it('有搜索条件或还没选对象时保留原空状态', () => {
    expect(policyGroupListEmptyText({ objectSelected: true, search: 'cpu' })).toBeNull();
    expect(policyGroupListEmptyText({ objectSelected: false, search: '' })).toBeNull();
  });
});