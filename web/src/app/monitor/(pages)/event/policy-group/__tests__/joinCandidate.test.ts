import { describe, expect, it } from 'vitest';

import {
  candidateBelongsToOtherOrganization,
  joinCandidateCheckboxDisabled,
  joinCandidateGroupLabel,
} from '../joinCandidate';

describe('加入实例候选', () => {
  it('organization 不包含当前组织时不可勾选', () => {
    expect(candidateBelongsToOtherOrganization([2, 3], '1')).toBe(true);
    expect(candidateBelongsToOtherOrganization(['1', 2], 1)).toBe(false);
    expect(candidateBelongsToOtherOrganization(undefined, '1')).toBe(true);
    expect(candidateBelongsToOtherOrganization([2], '')).toBe(false);
    expect(
      joinCandidateCheckboxDisabled({ belongsToOtherOrganization: true, joinedHere: false })
    ).toBe(true);
    expect(
      joinCandidateCheckboxDisabled({ belongsToOtherOrganization: false, joinedHere: true })
    ).toBe(true);
    expect(
      joinCandidateCheckboxDisabled({ belongsToOtherOrganization: false, joinedHere: false })
    ).toBe(false);
  });

  it('其他组织已在组时显示只读组名，否则说明属于其他组织', () => {
    expect(
      joinCandidateGroupLabel({
        belongsToOtherOrganization: true,
        policyGroupName: '子组织默认告警',
        joinedHere: false,
      })
    ).toEqual({ kind: 'other-readonly', text: '已在 子组织默认告警（只读）' });
    expect(
      joinCandidateGroupLabel({
        belongsToOtherOrganization: true,
        policyGroupName: '',
        joinedHere: false,
      })
    ).toEqual({ kind: 'other-empty', text: '属于其他组织' });
    expect(
      joinCandidateGroupLabel({
        belongsToOtherOrganization: false,
        policyGroupName: '',
        joinedHere: false,
      })
    ).toEqual({ kind: 'empty', text: '未加入' });
    expect(
      joinCandidateGroupLabel({
        belongsToOtherOrganization: false,
        policyGroupName: '父组织默认告警',
        joinedHere: false,
      })
    ).toEqual({ kind: 'named', text: '已在 父组织默认告警' });
  });
});
