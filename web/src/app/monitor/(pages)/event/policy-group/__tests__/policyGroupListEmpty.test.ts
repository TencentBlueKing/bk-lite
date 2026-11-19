import { describe, expect, it } from 'vitest';

import {
  POLICY_GROUP_DEFAULT_REMOVED_EMPTY,
  POLICY_GROUP_LIST_EMPTY,
  appliedPolicyGroupSearch,
  policyGroupListEmptyText,
} from '../policyGroupListEmpty';

describe('策略组列表空状态', () => {
  it('选中对象且没有搜索时说明默认组会在接入时生成', () => {
    expect(policyGroupListEmptyText({ objectSelected: true, search: '' })).toBe(POLICY_GROUP_LIST_EMPTY);
    expect(policyGroupListEmptyText({ objectSelected: true, search: '  ' })).toBe(POLICY_GROUP_LIST_EMPTY);
  });

  it('默认组已删除时不再承诺接入会重新生成', () => {
    expect(
      policyGroupListEmptyText({ objectSelected: true, search: '', defaultRemoved: true })
    ).toBe(POLICY_GROUP_DEFAULT_REMOVED_EMPTY);
  });

  it('有搜索条件或还没选对象时保留原空状态', () => {
    expect(policyGroupListEmptyText({ objectSelected: true, search: 'cpu', defaultRemoved: true })).toBeNull();
    expect(policyGroupListEmptyText({ objectSelected: false, search: '' })).toBeNull();
  });

  it('搜索使用本次输入的值，清除传入空字符串就清空', () => {
    expect(appliedPolicyGroupSearch('  cpu  ')).toBe('cpu');
    expect(appliedPolicyGroupSearch('')).toBe('');
    expect(appliedPolicyGroupSearch(undefined)).toBe('');
  });
});