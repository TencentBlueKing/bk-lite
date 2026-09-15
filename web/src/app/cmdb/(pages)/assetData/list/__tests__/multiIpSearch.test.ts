import { describe, expect, it } from 'vitest';

import {
  MULTI_IP_SEARCH_LIMIT,
  collectMultiIpSearchNotices,
  formatMultiIpInputValue,
  isMultiIpSearchAttr,
  normalizeMultiIpPaste,
  parseMultiIpSearchInput,
  resolveMultiIpSearch,
} from '../multiIpSearch';

describe('多 IP 检索解析', () => {
  it('仅内网 IP / 外网 IP 字段启用', () => {
    expect(isMultiIpSearchAttr('ip_addr')).toBe(true);
    expect(isMultiIpSearchAttr('public_ip')).toBe(true);
    expect(isMultiIpSearchAttr('inst_name')).toBe(false);
    expect(isMultiIpSearchAttr('remark')).toBe(false);
  });

  it('英文逗号、中文逗号、空格、换行混用都能拆开并去重', () => {
    expect(
      parseMultiIpSearchInput(
        '10.10.1.134，10.10.1.135\n10.10.1.134 10.10.1.136\r\n10.10.1.137,10.10.1.138',
      ),
    ).toEqual({
      ips: [
        '10.10.1.134',
        '10.10.1.135',
        '10.10.1.136',
        '10.10.1.137',
        '10.10.1.138',
      ],
      invalidCount: 0,
      truncated: false,
    });
  });

  it('中文逗号与分号也可拆分，非法 token 不导致失败', () => {
    expect(
      parseMultiIpSearchInput('10.10.1.134，abc;10.10.1.135,10.0.0.0/24,10.0.0.1:22'),
    ).toEqual({
      ips: ['10.10.1.134', '10.10.1.135'],
      invalidCount: 3,
      truncated: false,
    });
  });

  it('超过上限时截断', () => {
    const ips = Array.from({ length: MULTI_IP_SEARCH_LIMIT + 3 }, (_, index) => {
      const octet = index + 1;
      return `10.0.${Math.floor(octet / 256)}.${octet % 256}`;
    });
    const parsed = parseMultiIpSearchInput(ips.join(','));
    expect(parsed.ips).toHaveLength(MULTI_IP_SEARCH_LIMIT);
    expect(parsed.truncated).toBe(true);
    expect(parsed.ips[0]).toBe('10.0.0.1');
  });

  it('单个 IP 保持精确/模糊，多个 IP 走 str[]', () => {
    expect(resolveMultiIpSearch('ip_addr', '10.10.1.134', false)).toEqual({
      action: 'search',
      condition: { field: 'ip_addr', type: 'str*', value: '10.10.1.134' },
      parsed: { ips: ['10.10.1.134'], invalidCount: 0, truncated: false },
    });
    expect(resolveMultiIpSearch('public_ip', '10.10.1.134', true)).toEqual({
      action: 'search',
      condition: { field: 'public_ip', type: 'str=', value: '10.10.1.134' },
      parsed: { ips: ['10.10.1.134'], invalidCount: 0, truncated: false },
    });
    expect(
      resolveMultiIpSearch('ip_addr', '10.10.1.134,10.10.1.135', false),
    ).toEqual({
      action: 'search',
      condition: {
        field: 'ip_addr',
        type: 'str[]',
        value: ['10.10.1.134', '10.10.1.135'],
      },
      parsed: {
        ips: ['10.10.1.134', '10.10.1.135'],
        invalidCount: 0,
        truncated: false,
      },
    });
  });

  it('空输入清除条件，全非法则拒绝查询', () => {
    expect(resolveMultiIpSearch('ip_addr', '  ')).toMatchObject({
      action: 'clear',
      condition: { field: 'ip_addr' },
    });
    expect(resolveMultiIpSearch('ip_addr', 'abc,10.0.0.0/24')).toMatchObject({
      action: 'reject',
      condition: null,
      parsed: { ips: [], invalidCount: 2, truncated: false },
    });
  });

  it('粘贴时把逗号、空格、换行都收成英文逗号', () => {
    expect(
      normalizeMultiIpPaste('10.10.1.134，10.10.1.135\n10.10.1.136 10.10.1.137'),
    ).toBe('10.10.1.134,10.10.1.135,10.10.1.136,10.10.1.137');
    expect(formatMultiIpInputValue(['10.10.1.134', '10.10.1.135'])).toBe(
      '10.10.1.134,10.10.1.135',
    );
  });

  it('全非法只提示没有可搜 IP，混入非法则提示忽略数量', () => {
    expect(
      collectMultiIpSearchNotices(resolveMultiIpSearch('ip_addr', 'abc')),
    ).toEqual([{ id: 'FilterBar.multiIpNoValid' }]);
    expect(
      collectMultiIpSearchNotices(
        resolveMultiIpSearch('ip_addr', '10.10.1.134,abc,10.10.1.135'),
      ),
    ).toEqual([
      { id: 'FilterBar.multiIpIgnoredInvalid', values: { count: 1 } },
    ]);
    expect(collectMultiIpSearchNotices(resolveMultiIpSearch('ip_addr', ''))).toEqual(
      [],
    );
  });
});
