import { describe, expect, it } from 'vitest';

import { jobTargetOperatingSystems } from '../lib/job-target-operating-systems';

function form(operatingSystems: Array<'linux' | 'windows'>) {
  return [{
    input_schema: {
      type: 'object' as const,
      properties: {
        targets: {
          type: 'array' as const,
          'x-target-binding': {
            mode: 'runtime' as const,
            allowedSources: ['node_mgmt' as const, 'job_mgmt' as const],
            allowedOperatingSystems: operatingSystems,
            minCount: 1,
            maxCount: 100,
          },
        },
      },
    },
  }];
}

describe('作业节点可选操作系统', () => {
  it('上游表单只允许 Linux 时禁用 Windows', () => {
    expect(jobTargetOperatingSystems({
      targets: '${workflow.input.targets}',
      triggers: form(['linux']),
    })).toEqual(['linux']);
  });

  it('上游表单只允许 Windows 时禁用 Linux', () => {
    expect(jobTargetOperatingSystems({
      targets: '${workflow.input.targets}',
      triggers: form(['windows']),
    })).toEqual(['windows']);
  });

  it('上游表单两种系统都允许时不收窄', () => {
    expect(jobTargetOperatingSystems({
      targets: '${workflow.input.targets}',
      triggers: form(['linux', 'windows']),
    })).toEqual(['linux', 'windows']);
  });

  it('目标没有指向表单字段时不收窄', () => {
    expect(jobTargetOperatingSystems({
      targets: ['node:1'],
      triggers: form(['linux']),
    })).toBeUndefined();
  });
});
