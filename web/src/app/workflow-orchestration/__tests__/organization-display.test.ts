import { describe, expect, it } from 'vitest';

import { organizationDisplayText } from '../lib/organization-display';

const groups = [
  { id: '1', name: '集团' },
  { id: '7', name: '当前组织', parentId: '1' },
  { id: '8', name: '其他组织' },
];

describe('流程组织展示', () => {
  it('用斜杠拼完整路径，多个组织用中文逗号隔开', () => {
    expect(organizationDisplayText([7, '8'], groups)).toBe('集团/当前组织，其他组织');
  });

  it('空组织或找不到的组织显示占位', () => {
    expect(organizationDisplayText([], groups)).toBe('--');
    expect(organizationDisplayText([99], groups)).toBe('--');
    expect(organizationDisplayText(undefined, groups)).toBe('--');
  });
});
