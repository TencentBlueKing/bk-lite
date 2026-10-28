import { describe, expect, it } from 'vitest';
import { buildSearchJumpUrl } from '../buildSearchJumpUrl';

describe('buildSearchJumpUrl', () => {
  it('有 jump_query 时使用冻结窗口，并把秒转成毫秒', () => {
    const url = buildSearchJumpUrl({
      jumpQuery: {
        query: 'level:error AND service:="order"',
        window_start: 1761550000,
        window_end: 1761550300,
      },
      fallbackQuery: 'level:error | stats count()',
      fallbackStart: '1',
      fallbackEnd: '2',
      logGroups: ['g1', 'g2'],
    });

    expect(url.startsWith('/log/search?')).toBe(true);
    const params = new URLSearchParams(url.slice('/log/search?'.length));
    expect(params.get('query')).toBe('level:error AND service:="order"');
    expect(params.get('query')).not.toContain('| stats');
    expect(params.get('startTime')).toBe('1761550000000');
    expect(params.get('endTime')).toBe('1761550300000');
    expect(params.getAll('log_groups')).toEqual(['g1', 'g2']);
  });

  it('没有 jump_query 时退回原查询和时间窗', () => {
    const url = buildSearchJumpUrl({
      fallbackQuery: 'level:error',
      fallbackStart: '111',
      fallbackEnd: '222',
      logGroups: ['g1'],
    });
    const params = new URLSearchParams(url.slice('/log/search?'.length));
    expect(params.get('query')).toBe('level:error');
    expect(params.get('startTime')).toBe('111');
    expect(params.get('endTime')).toBe('222');
    expect(params.get('query')).not.toContain('stats');
  });
});