import { describe, expect, it } from 'vitest';
import { policyGroupAccessNotes } from '../policyGroupAccessNotes';

const rules = [
  { name: '主机 CPU 使用率过高', plugin_id: 10, metric_name: 'cpu' },
  { name: '主机内存使用率过高', plugin_id: 10, metric_name: 'mem' },
  { name: '磁盘使用率过高', plugin_id: 11, metric_name: 'disk' },
];

describe('policyGroupAccessNotes', () => {
  it('stays quiet when every rule for this plugin has a metric', () => {
    expect(policyGroupAccessNotes(rules, 10, ['cpu', 'mem'])).toEqual({
      kind: 'none',
    });
  });

  it('lists only this plugin rules that will not have data', () => {
    expect(policyGroupAccessNotes(rules, 10, ['cpu'])).toEqual({
      kind: 'missing',
      names: ['主机内存使用率过高'],
    });
  });

  it('says the group has no rule for this plugin', () => {
    expect(policyGroupAccessNotes(rules, 12, ['cpu'])).toEqual({
      kind: 'no-plugin-rules',
    });
  });

  it('does not warn about missing data before the metric catalog loads', () => {
    expect(policyGroupAccessNotes(rules, 10, [])).toEqual({ kind: 'none' });
  });

  it('requires every condition metric of a multi-metric rule', () => {
    const multi = [
      {
        name: 'CPU 与内存双高',
        plugin_id: 10,
        metric_name: 'cpu',
        metric_names: ['cpu', 'mem'],
      },
    ];
    expect(policyGroupAccessNotes(multi, 10, ['cpu', 'mem'])).toEqual({
      kind: 'none',
    });
    expect(policyGroupAccessNotes(multi, 10, ['cpu'])).toEqual({
      kind: 'missing',
      names: ['CPU 与内存双高'],
    });
  });
});
