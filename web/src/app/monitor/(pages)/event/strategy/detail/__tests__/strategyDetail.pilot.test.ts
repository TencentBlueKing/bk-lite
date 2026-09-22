import { describe, expect, it } from 'vitest';

import { buildStrategyDetailContext } from '../strategyDetail.pilot';

describe('strategyDetail.pilot', () => {
  it('puts display names in notice-people and keeps thresholds in the detail section', () => {
    const ctx = buildStrategyDetailContext({
      name: 'CPU 高',
      objectName: '主机',
      source: { type: 'instance', values: ['a', 'b'] },
      expression: 'cpu_usage',
      thresholds: [{ level: 'critical', method: '>=', value: 80 }],
      period: 5,
      periodUnit: 'min',
      noticeUsers: ['u1'],
      handlers: ['u2'],
      userList: [
        { id: 'u1', username: 'zhangsan', display_name: '张三' },
        { id: 'u2', username: 'lisi', display_name: '李四' },
      ],
    });
    const detail = (ctx.sections || []).find((section) => section.id === 'strategy-detail')?.content || '';
    const people = (ctx.sections || []).find((section) => section.id === 'notice-people')?.content || '';
    expect(detail).toContain('阈值: critical >= 80');
    expect(detail).toContain('表达式: cpu_usage');
    expect(detail).not.toContain('张三');
    expect(people).toContain('张三');
    expect(people).toContain('李四');
    expect(people).not.toContain('zhangsan');
    expect(people).not.toContain('u1');
  });
});
