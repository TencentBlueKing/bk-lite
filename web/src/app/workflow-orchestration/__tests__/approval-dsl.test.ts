import { describe, expect, it } from 'vitest';

import { configureApprovalTask } from '../lib/approval-dsl';
import type { ConductorDefinition } from '../lib/types';

const definition: ConductorDefinition = {
  name: 'approval', version: 1, schemaVersion: 2,
  tasks: [
    {
      name: 'manual_approval', taskReferenceName: 'approval', type: 'HUMAN',
      inputParameters: { interactionType: 'APPROVAL', title: '旧标题', candidates: ['admin'], publicContext: {} },
    },
    {
      name: 'approval_decision', taskReferenceName: 'approval_decision', type: 'SWITCH',
      inputParameters: { decision: '${approval.output.approved}' },
      decisionCases: { true: [], false: [] }, defaultCase: [],
    },
  ],
};

describe('审批节点配置', () => {
  it('保存真实候选人、公开上下文并在启用超时时生成超时分支', () => {
    const next = configureApprovalTask(definition, 'approval', {
      title: '生产变更确认',
      description: '核对巡检结果',
      candidates: ['alice', 'bob'],
      publicContext: { host_count: '${scan.output.count}' },
      timeoutSeconds: 3600,
    });

    expect(next.tasks[0].inputParameters).toMatchObject({
      title: '生产变更确认',
      candidates: ['alice', 'bob'],
      publicContext: { host_count: '${scan.output.count}' },
      timeoutSeconds: 3600,
    });
    expect(next.tasks[1].decisionCases).toHaveProperty('timeout', []);
  });

  it('关闭超时会移除超时输入和分支', () => {
    const enabled = configureApprovalTask(definition, 'approval', {
      title: '确认', candidates: ['alice'], publicContext: {}, timeoutSeconds: 60,
    });
    const disabled = configureApprovalTask(enabled, 'approval', {
      title: '确认', candidates: ['alice'], publicContext: {},
    });

    expect(disabled.tasks[0].inputParameters).not.toHaveProperty('timeoutSeconds');
    expect(disabled.tasks[1].decisionCases).not.toHaveProperty('timeout');
  });
});
