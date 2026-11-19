import { describe, expect, it } from 'vitest';

import {
  POLICY_GROUP_OTHER_ORG_HINT,
  isPolicyGroupMembershipReadOnly,
  policyGroupMembershipLabel,
} from '../policyGroupMembership';

describe('策略组只读成员', () => {
  it('只有后端标明只读时才收起修改', () => {
    expect(isPolicyGroupMembershipReadOnly({ read_only: true })).toBe(true);
    expect(isPolicyGroupMembershipReadOnly({ read_only: false })).toBe(false);
    expect(isPolicyGroupMembershipReadOnly(null)).toBe(false);
  });

  it('组名后带上所属组织，没有组名时不拼组织', () => {
    expect(
      policyGroupMembershipLabel({
        group_name: '主机默认告警',
        group_organization_name: '研发',
      })
    ).toBe('主机默认告警（研发）');
    expect(policyGroupMembershipLabel({ group_name: '主机默认告警' })).toBe('主机默认告警');
    expect(policyGroupMembershipLabel({ group_name: '', group_organization_name: '研发' })).toBe('');
  });

  it('提示切到所属组织后再改', () => {
    expect(POLICY_GROUP_OTHER_ORG_HINT).toBe('这台实例属于其他组织，策略组请切换到所属组织后修改');
  });
});
