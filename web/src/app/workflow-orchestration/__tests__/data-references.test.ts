import { describe, expect, it } from 'vitest';

import {
  buildDataReferenceOptions,
  compileNodeInputBinding,
  compatibleDataReferences,
  dataReferenceCompatibility,
  dataReferencePreview,
  parseNodeInputBinding,
  resolveNodeTestInputs,
} from '../lib/data-references';
import type { AtomCatalogItem, ConductorDefinition, JsonSchema } from '../lib/types';

const atoms: AtomCatalogItem[] = [
  {
    key: 'source', name: '来源', category: '测试', description: '',
    output_schema: { type: 'object', properties: { count: { type: 'integer' }, hosts: { type: 'array', items: { type: 'object' } } } },
  },
  { key: 'target', name: '目标', category: '测试', description: '', input_schema: { type: 'object' } },
];

describe('节点数据选择器', () => {
  it('只返回工作流输入与可达前序节点输出', () => {
    const definition: ConductorDefinition = {
      name: 'data-flow', version: 1, schemaVersion: 2,
      tasks: [
        { name: 'source', taskReferenceName: 'before', type: 'SIMPLE', inputParameters: {} },
        { name: 'target', taskReferenceName: 'current', type: 'SIMPLE', inputParameters: {} },
        { name: 'source', taskReferenceName: 'after', type: 'SIMPLE', inputParameters: {} },
      ],
    };
    const workflowSchema: JsonSchema = { type: 'object', properties: { threshold: { type: 'integer' } } };

    const options = buildDataReferenceOptions(definition, 'current', atoms, workflowSchema);

    expect(options.map((option) => option.value)).toContain('${workflow.input.threshold}');
    expect(options.map((option) => option.value)).toContain('${before.output.count}');
    expect(options.map((option) => option.value)).not.toContain('${after.output.count}');
  });

  it('画布模式按连线而不是任务数组顺序确定上游数据', () => {
    const definition: ConductorDefinition = {
      name: 'edge-data-flow', version: 1, schemaVersion: 2,
      tasks: [
        { name: 'target', taskReferenceName: 'current', type: 'SIMPLE', inputParameters: {} },
        { name: 'source', taskReferenceName: 'connected_before', type: 'SIMPLE', inputParameters: {} },
        { name: 'source', taskReferenceName: 'unconnected', type: 'SIMPLE', inputParameters: {} },
      ],
    };

    const options = buildDataReferenceOptions(
      definition,
      'current',
      atoms,
      {},
      undefined,
      [
        { source: 'trigger_form', target: 'connected_before' },
        { source: 'connected_before', target: 'current' },
      ],
    );
    const values = options.map((option) => option.value);

    expect(values).toContain('${connected_before.output}');
    expect(values).toContain('${connected_before.output.count}');
    expect(values).not.toContain('${unconnected.output.count}');
    expect(options.findIndex((option) => option.source === 'connected_before')).toBeLessThan(
      options.findIndex((option) => option.sourceKind === 'system'),
    );
  });

  it('画布分支内隔离兄弟输出，汇聚后可引用全部上游输出', () => {
    const definition: ConductorDefinition = {
      name: 'edge-branches', version: 1, schemaVersion: 2,
      tasks: [
        { name: 'source', taskReferenceName: 'root', type: 'SIMPLE', inputParameters: {} },
        { name: 'source', taskReferenceName: 'left', type: 'SIMPLE', inputParameters: {} },
        { name: 'target', taskReferenceName: 'right', type: 'SIMPLE', inputParameters: {} },
        { name: 'target', taskReferenceName: 'merged', type: 'SIMPLE', inputParameters: {} },
      ],
    };
    const edges = [
      { source: 'root', target: 'left' },
      { source: 'root', target: 'right' },
      { source: 'left', target: 'merged' },
      { source: 'right', target: 'merged' },
    ];

    const rightValues = buildDataReferenceOptions(definition, 'right', atoms, {}, undefined, edges).map((option) => option.value);
    const mergedValues = buildDataReferenceOptions(definition, 'merged', atoms, {}, undefined, edges).map((option) => option.value);

    expect(rightValues).toContain('${root.output.count}');
    expect(rightValues).not.toContain('${left.output.count}');
    expect(mergedValues).toContain('${left.output.count}');
    expect(mergedValues).toContain('${root.output.count}');
  });

  it('并行分支内部不会看到兄弟分支输出', () => {
    const definition: ConductorDefinition = {
      name: 'branches', version: 1, schemaVersion: 2,
      tasks: [{
        name: 'parallel', taskReferenceName: 'parallel', type: 'FORK_JOIN',
        forkTasks: [
          [{ name: 'source', taskReferenceName: 'left', type: 'SIMPLE', inputParameters: {} }],
          [{ name: 'target', taskReferenceName: 'right', type: 'SIMPLE', inputParameters: {} }],
        ],
      }],
    };

    const options = buildDataReferenceOptions(definition, 'right', atoms, {});

    expect(options.map((option) => option.value)).not.toContain('${left.output.count}');
  });

  it('分支汇合后的节点不会直接看到分支内部输出', () => {
    const definition: ConductorDefinition = {
      name: 'branch-join', version: 1, schemaVersion: 2,
      tasks: [
        {
          name: 'condition', taskReferenceName: 'condition', type: 'SWITCH', inputParameters: {},
          decisionCases: { yes: [{ name: 'source', taskReferenceName: 'branch_source', type: 'SIMPLE', inputParameters: {} }] },
          defaultCase: [],
        },
        { name: 'target', taskReferenceName: 'after_join', type: 'SIMPLE', inputParameters: {} },
      ],
    };

    const options = buildDataReferenceOptions(definition, 'after_join', atoms, {});

    expect(options.map((option) => option.value)).not.toContain('${branch_source.output.count}');
  });

  it('显式 JOIN 汇合后可引用 joinOn 声明的分支输出', () => {
    const definition: ConductorDefinition = {
      name: 'parallel-join', version: 1, schemaVersion: 2,
      tasks: [
        {
          name: 'parallel', taskReferenceName: 'parallel', type: 'FORK_JOIN',
          forkTasks: [
            [{ name: 'source', taskReferenceName: 'linux_scan', type: 'SIMPLE', inputParameters: {} }],
            [{ name: 'source', taskReferenceName: 'windows_scan', type: 'SIMPLE', inputParameters: {} }],
          ],
        },
        { name: 'join', taskReferenceName: 'scan_join', type: 'JOIN', joinOn: ['linux_scan', 'windows_scan'] },
        { name: 'target', taskReferenceName: 'analyze', type: 'SIMPLE', inputParameters: {} },
      ],
    };

    const values = buildDataReferenceOptions(definition, 'analyze', atoms, {}).map((option) => option.value);

    expect(values).toContain('${linux_scan.output.count}');
    expect(values).toContain('${windows_scan.output.count}');
  });

  it('按目标字段类型过滤引用', () => {
    const references = [
      { label: '数量', value: '${before.output.count}', type: 'integer', source: 'before' },
      { label: '主机', value: '${before.output.hosts}', type: 'array', source: 'before' },
    ];

    expect(compatibleDataReferences(references, { type: 'number' }).map((item) => item.value)).toEqual(['${before.output.count}']);
    expect(compatibleDataReferences([{ ...references[0], type: 'number' }], { type: 'integer' })).toEqual([]);
  });

  it('敏感引用只能绑定到声明兼容的字段', () => {
    const reference = { label: '令牌', value: '${workflow.input.token}', type: 'string', source: '流程输入', sensitive: true };

    expect(dataReferenceCompatibility(reference, { type: 'string' })).toEqual({ compatible: false, reason: '目标字段未声明可接收敏感值' });
    expect(dataReferenceCompatibility(reference, { type: 'string', secretCompatible: true })).toEqual({ compatible: true });
  });

  it('系统上下文由平台自动注入，且不存在流程常量来源', () => {
    const definition: ConductorDefinition = {
      name: 'contract', version: 1, schemaVersion: 2,
      tasks: [{ name: 'target', taskReferenceName: 'current', type: 'SIMPLE', inputParameters: {} }],
    };

    const values = buildDataReferenceOptions(definition, 'current', atoms, {}).map((option) => option.value);

    expect(values).not.toContain('${workflow.variables.timeout}');
    expect(values).toContain('${system.execution_id}');
  });

  it('固定值、整值引用和文本模板可以确定性往返', () => {
    expect(parseNodeInputBinding(42)).toEqual({ kind: 'literal', value: 42 });
    expect(parseNodeInputBinding('${workflow.input.threshold}')).toEqual({ kind: 'reference', expression: '${workflow.input.threshold}' });
    expect(parseNodeInputBinding('环境 ${workflow.input.environment}')).toEqual({ kind: 'template', template: '环境 ${workflow.input.environment}' });
    expect(compileNodeInputBinding(parseNodeInputBinding('${before.output.count}'))).toBe('${before.output.count}');
  });

  it('左侧输入面板从触发数据和上游测试输出生成预览', () => {
    expect(dataReferencePreview(
      { label: '阈值', value: '${workflow.input.threshold}', source: '触发输入', sourceKind: 'trigger', sourceReference: 'workflow.input', path: 'threshold' },
      { threshold: 85 },
      {},
    )).toBe(85);
    expect(dataReferencePreview(
      { label: 'CPU', value: '${scan.output.metrics.cpu}', source: 'scan', sourceKind: 'node_output', sourceReference: 'scan', path: 'metrics.cpu' },
      {},
      { scan: { metrics: { cpu: 42 } } },
    )).toBe(42);
  });

  it('节点测试会解析触发输入、上游输出和文本模板，并报告缺失来源', () => {
    const resolved = resolveNodeTestInputs(
      {
        threshold: '${workflow.input.threshold}',
        completeOutput: '${scan.output}',
        metrics: '${scan.output.metrics}',
        summary: '主机 ${workflow.input.host} CPU ${scan.output.metrics.cpu}',
        runtimeActor: '${workflow.input.actor}',
        missing: '${unknown.output.value}',
      },
      { threshold: 85, host: '10.10.90.120' },
      { scan: { metrics: { cpu: 42 } } },
    );

    expect(resolved.value).toMatchObject({
      threshold: 85,
      completeOutput: { metrics: { cpu: 42 } },
      metrics: { cpu: 42 },
      summary: '主机 10.10.90.120 CPU 42',
      runtimeActor: '${workflow.input.actor}',
    });
    expect(resolved.unresolved).toEqual(['${unknown.output.value}']);
  });
});
