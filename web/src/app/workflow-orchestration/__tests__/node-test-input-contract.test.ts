import { describe, expect, it } from 'vitest';

import { buildNodeTestInputContract, materializeNodeTestInputs } from '../lib/node-test-input-contract';
import type { ConductorTask, JsonSchema } from '../lib/types';

const jobSchema: JsonSchema = {
  type: 'object',
  properties: {
    targets: { type: 'array', title: '目标主机', minItems: 1, maxItems: 100 },
    script_type: { type: 'string' },
    script_content: { type: 'string' },
  },
  required: ['targets', 'script_type', 'script_content'],
};

const triggerSchema: JsonSchema = {
  type: 'object',
  properties: {
    targets: {
      type: 'array',
      title: '目标主机',
      'x-widget': 'target-selector',
      'x-target-binding': {
        mode: 'runtime',
        allowedSources: ['job_mgmt', 'node_mgmt'],
        allowedOperatingSystems: ['linux', 'windows'],
        minCount: 1,
        maxCount: 100,
      },
    },
    report_template: { type: 'object', title: '报告模板', 'x-widget': 'file-upload' },
  },
  required: ['targets', 'report_template'],
};

function task(inputParameters: Record<string, unknown>): ConductorTask {
  return { name: 'bklite_job_execute', taskReferenceName: 'job_execute', type: 'SIMPLE', inputParameters };
}

describe('作业节点测试输入契约', () => {
  it('引用触发器目标时复用触发器字段并保留其来源声明', () => {
    const contract = buildNodeTestInputContract(task({ targets: '${workflow.input.targets}' }), jobSchema, triggerSchema);

    expect(contract.schema.properties?.targets?.['x-target-binding']?.allowedSources).toEqual(['job_mgmt', 'node_mgmt']);
    expect(materializeNodeTestInputs(contract, { targets: '${workflow.input.targets}' }, {
      targets: ['manual:7'],
    }, {})).toEqual({
      workflowInputs: {
        targets: ['manual:7'],
      },
      nodeInputs: {
        targets: ['manual:7'],
      },
      unresolved: [],
    });
  });

  it('作业节点未配置目标时生成仅作业平台的测试选择器', () => {
    const contract = buildNodeTestInputContract(task({ targets: [] }), jobSchema, triggerSchema);
    const [field] = Object.keys(contract.schema.properties || {});

    expect(field).toBe('__node_input__targets');
    expect(contract.nodeOverrides[field]).toBe('targets');
    expect(contract.schema.properties?.[field]['x-target-binding']?.allowedSources).toEqual(['job_mgmt']);

    expect(materializeNodeTestInputs(contract, { targets: [] }, { [field]: ['manual:7'] }, {})).toEqual({
      workflowInputs: {},
      nodeInputs: { targets: ['manual:7'] },
      unresolved: [],
    });
  });

  it('已配置固定目标时仍提供确认用目标字段', () => {
    const contract = buildNodeTestInputContract(task({ targets: ['manual:8'] }), jobSchema, triggerSchema);
    const [field] = Object.keys(contract.schema.properties || {});

    expect(field).toBe('__node_input__targets');
    expect(contract.nodeOverrides[field]).toBe('targets');
    expect(contract.schema.properties?.[field]['x-target-binding']?.allowedSources).toEqual(['job_mgmt']);
    expect(materializeNodeTestInputs(contract, { targets: ['manual:8'] }, { [field]: ['manual:8', 'manual:9'] }, {})).toEqual({
      workflowInputs: {},
      nodeInputs: { targets: ['manual:8', 'manual:9'] },
      unresolved: [],
    });
  });
});
