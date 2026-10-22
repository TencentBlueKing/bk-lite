import { describe, expect, it } from 'vitest';

import { buildWorkflowFlow, implicitCanvasEdges } from '../lib/canvas-dsl';
import {
  coerceResolvedValueForSchema,
  buildDataReferenceOptions,
  compileNodeInputBinding,
  resolveTriggerGroupLabel,
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

  it('右上角添加后自动画出的触发器连线对下游输入可见', () => {
    const definition: ConductorDefinition = {
      name: 'auto-edge', version: 1, schemaVersion: 2,
      tasks: [{ name: 'source', taskReferenceName: 'job_execute', type: 'SIMPLE', inputParameters: {} }],
    };
    const workflowSchema: JsonSchema = { type: 'object', properties: { triggered_at: { type: 'string', title: '触发时间' } } };
    const metadata = {
      trigger_nodes: [{
        id: 'trigger_schedule',
        name: '定时触发器',
        trigger_type: 'SCHEDULE' as const,
        input_schema: workflowSchema,
        config: {},
      }],
      edges: [] as [],
    };
    const stored = implicitCanvasEdges(definition, metadata);
    const edges = buildWorkflowFlow(definition, { ...metadata, edges: stored }).edges;

    const values = buildDataReferenceOptions(definition, 'job_execute', atoms, workflowSchema, undefined, edges).map((option) => option.value);

    expect(edges.map((edge) => [edge.source, edge.target])).toEqual([['trigger_schedule', 'job_execute']]);
    expect(values).toContain('${workflow.input.triggered_at}');
    expect(values).toContain('${system.execution_id}');
  });

  it('画布上走不回触发器时只保留运行信息和已连接的上游输出', () => {
    const definition: ConductorDefinition = {
      name: 'unwired-trigger', version: 1, schemaVersion: 2,
      tasks: [
        { name: 'source', taskReferenceName: 'job_execute', type: 'SIMPLE', inputParameters: {} },
        { name: 'source', taskReferenceName: 'island', type: 'SIMPLE', inputParameters: {} },
        { name: 'target', taskReferenceName: 'document_render', type: 'SIMPLE', inputParameters: {} },
      ],
    };
    const workflowSchema: JsonSchema = { type: 'object', properties: { triggered_at: { type: 'string', title: '触发时间' } } };
    const edges = [
      { source: 'trigger_schedule', target: 'job_execute' },
      { source: 'island', target: 'document_render' },
    ];

    const values = buildDataReferenceOptions(definition, 'document_render', atoms, workflowSchema, undefined, edges).map((option) => option.value);

    expect(values).not.toContain('${workflow.input.triggered_at}');
    expect(values).not.toContain('${job_execute.output}');
    expect(values).toContain('${island.output}');
    expect(values).toContain('${system.execution_id}');
  });

  it('沿连线走回触发器后可以看到入口字段', () => {
    const definition: ConductorDefinition = {
      name: 'wired-trigger', version: 1, schemaVersion: 2,
      tasks: [
        { name: 'source', taskReferenceName: 'job_execute', type: 'SIMPLE', inputParameters: {} },
        { name: 'target', taskReferenceName: 'document_render', type: 'SIMPLE', inputParameters: {} },
      ],
    };
    const workflowSchema: JsonSchema = { type: 'object', properties: { triggered_at: { type: 'string', title: '触发时间' } } };
    const edges = [
      { source: 'trigger_schedule', target: 'job_execute' },
      { source: 'job_execute', target: 'document_render' },
    ];

    const values = buildDataReferenceOptions(definition, 'document_render', atoms, workflowSchema, undefined, edges).map((option) => option.value);

    expect(values).toContain('${workflow.input.triggered_at}');
    expect(values).toContain('${job_execute.output}');
    expect(values).toContain('${system.execution_id}');
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
      { label: '全部输出', value: '${before.output}', type: 'object', source: 'before' },
    ];

    expect(compatibleDataReferences(references, { type: 'number' }).map((item) => item.value)).toEqual(['${before.output.count}']);
    expect(compatibleDataReferences([{ ...references[0], type: 'number' }], { type: 'integer' })).toEqual([]);
    expect(compatibleDataReferences(references, { type: 'string' }).map((item) => item.value)).toEqual([]);
    expect(compatibleDataReferences(
      [...references, { label: '主机名', value: '${before.output.host}', type: 'string', source: 'before' }],
      { type: 'string' },
    ).map((item) => item.value)).toEqual(['${before.output.host}']);
    expect(compatibleDataReferences(references, { type: 'string', 'x-text-surface': 'coerce' }).map((item) => item.value)).toEqual([
      '${before.output.count}',
      '${before.output.hosts}',
      '${before.output}',
    ]);
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

    const options = buildDataReferenceOptions(definition, 'current', atoms, {});
    const values = options.map((option) => option.value);

    expect(values).not.toContain('${workflow.variables.timeout}');
    expect(values).toContain('${system.execution_id}');
    expect(options.find((option) => option.value === '${system.trigger_type}')?.displayName).toBe('触发类型');
    expect(options.find((option) => option.sourceKind === 'system')?.sourceLabel).toBe('运行信息');
  });

  it('上游分组按流程从前往后排列，字段名只用当前标题', () => {
    const definition: ConductorDefinition = {
      name: 'ordered-flow', version: 1, schemaVersion: 2,
      tasks: [
        { name: 'source', taskReferenceName: 'job_execute', type: 'SIMPLE', inputParameters: {} },
        { name: 'source', taskReferenceName: 'document_render', type: 'SIMPLE', inputParameters: {} },
        { name: 'target', taskReferenceName: 'notification', type: 'SIMPLE', inputParameters: {} },
      ],
    };
    const titledAtoms: AtomCatalogItem[] = [
      {
        key: 'source', name: '作业执行', category: '测试', description: '',
        output_schema: {
          type: 'object',
          properties: {
            artifact: {
              type: 'object',
              title: '生成文件',
              properties: { id: { type: 'string', title: '文件标识' } },
            },
          },
        },
      },
      { key: 'target', name: '对外通知', category: '测试', description: '', input_schema: { type: 'object' } },
    ];

    const options = buildDataReferenceOptions(
      definition,
      'notification',
      titledAtoms,
      { type: 'object', properties: { file: { type: 'object', title: '模板文件' } } },
      undefined,
      [
        { source: 'trigger_form', target: 'job_execute' },
        { source: 'job_execute', target: 'document_render' },
        { source: 'document_render', target: 'notification' },
      ],
      { job_execute: '作业执行', document_render: '文档生成' },
    );

    const sources = options.map((option) => option.sourceLabel);
    expect(sources.indexOf('触发输入')).toBeLessThan(sources.indexOf('作业执行'));
    expect(sources.indexOf('作业执行')).toBeLessThan(sources.indexOf('文档生成'));
    expect(sources.indexOf('文档生成')).toBeLessThan(sources.indexOf('运行信息'));
    expect(options.find((option) => option.value === '${document_render.output}')?.jsonPath).toBe('output');
    expect(options.find((option) => option.value === '${document_render.output}')?.displayName).toBe('全部输出');
    expect(options.find((option) => option.value === '${document_render.output.artifact.id}')?.displayName).toBe('文件标识');
    expect(options.find((option) => option.value === '${workflow.input.file}')?.displayName).toBe('模板文件');
  });

  it('同名上游节点在标题后附上引用名', () => {
    const definition: ConductorDefinition = {
      name: 'duplicate-names', version: 1, schemaVersion: 2,
      tasks: [
        { name: 'source', taskReferenceName: 'first_job', type: 'SIMPLE', inputParameters: {} },
        { name: 'source', taskReferenceName: 'second_job', type: 'SIMPLE', inputParameters: {} },
        { name: 'target', taskReferenceName: 'current', type: 'SIMPLE', inputParameters: {} },
      ],
    };

    const options = buildDataReferenceOptions(definition, 'current', atoms, {});
    const labels = options.filter((option) => option.jsonPath === 'output').map((option) => option.sourceLabel);

    expect(labels).toEqual(['来源 · first_job', '来源 · second_job']);
  });

  it('触发分组使用触发器节点名称，重名时附上引用', () => {
    const definition: ConductorDefinition = {
      name: 'named-trigger', version: 1, schemaVersion: 2,
      tasks: [
        { name: 'source', taskReferenceName: 'job_execute', type: 'SIMPLE', inputParameters: {} },
        { name: 'target', taskReferenceName: 'current', type: 'SIMPLE', inputParameters: {} },
      ],
    };
    const edges = [
      { source: 'trigger_form', target: 'job_execute' },
      { source: 'job_execute', target: 'current' },
    ];
    const schema: JsonSchema = { type: 'object', properties: { file: { type: 'object', title: '模板文件' } } };

    expect(resolveTriggerGroupLabel('current', [{ id: 'trigger_form', name: '表单触发器' }], edges, '触发输入')).toBe('表单触发器');
    const options = buildDataReferenceOptions(definition, 'current', atoms, schema, undefined, edges, { job_execute: '表单触发器' }, '表单触发器');
    expect(options.find((option) => option.value === '${workflow.input.file}')?.sourceLabel).toBe('表单触发器 · workflow.input');
    expect(options.find((option) => option.value === '${job_execute.output}')?.sourceLabel).toBe('表单触发器 · job_execute');
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

  it('string 目标字段会把非字符串解析结果强制成 JSON 文本', () => {
    expect(coerceResolvedValueForSchema({ metrics: { cpu: 42 } }, { type: 'string' })).toBe('{"metrics":{"cpu":42}}');
    expect(coerceResolvedValueForSchema(12, { type: 'string' })).toBe('12');
    expect(coerceResolvedValueForSchema({ metrics: { cpu: 42 } }, { type: 'object' })).toEqual({ metrics: { cpu: 42 } });
  });
});
