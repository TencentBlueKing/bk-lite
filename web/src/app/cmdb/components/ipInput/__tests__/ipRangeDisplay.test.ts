import { describe, expect, it } from 'vitest';

import {
  displayedIpFromOctets,
  ipOctetsFromValue,
  ipRangeDisplayNeedsSync,
} from '../ipRangeLimits';

describe('IP 段输入回写', () => {
  it('Form.List 第二行带着值挂载时，空格子仍需要同步', () => {
    expect(displayedIpFromOctets(['', '', '', ''])).toBe('');
    expect(
      ipRangeDisplayNeedsSync('', '', ['10.11.27.140', '10.11.27.147'])
    ).toBe(true);
    expect(ipOctetsFromValue('10.11.27.140')).toEqual(['10', '11', '27', '140']);
  });

  it('格子已经显示同一地址时不再同步', () => {
    expect(
      ipRangeDisplayNeedsSync('10.11.27.140', '10.11.27.147', [
        '10.11.27.140',
        '10.11.27.147',
      ])
    ).toBe(false);
  });
});
