import { describe, expect, it } from 'vitest';

import { buildWorkflowFlow, commonTriggerInputSchema, expandApprovalCanvasEdges } from '../lib/canvas-dsl';
import type { ConductorDefinition } from '../lib/types';

const definition: ConductorDefinition = {
  name: 'ordered-workflow',
  version: 1,
  schemaVersion: 2,
  tasks: [
    { name: 'bklite_notification', taskReferenceName: 'first', type: 'SIMPLE', inputParameters: { notification_type: 'EMAIL', channel_id: 1, body: 'first' } },
    { name: 'bklite_notification', taskReferenceName: 'second', type: 'SIMPLE', inputParameters: { notification_type: 'EMAIL', channel_id: 1, body: 'second' } },
    { name: 'bklite_notification', taskReferenceName: 'third', type: 'SIMPLE', inputParameters: { notification_type: 'EMAIL', channel_id: 1, body: 'third' } },
  ],
};

describe('画布连线与 Conductor DSL', () => {
  it('共享下游只暴露每个触发器都保证的输入字段', () => {
    const shared = { type: 'string' as const, title: '服务' };
    expect(commonTriggerInputSchema({
      trigger_nodes: [
        { id: 'form', name: '表单', trigger_type: 'FORM', input_schema: { type: 'object', properties: { service: shared, form_only: { type: 'string' } }, required: ['service'] }, config: {} },
        { id: 'hook', name: 'Webhook', trigger_type: 'WEBHOOK', input_schema: { type: 'object', properties: { service: shared, hook_only: { type: 'string' } }, required: [] }, config: {} },
      ],
    })).toEqual({ type: 'object', properties: { service: shared }, required: [], additionalProperties: false });
  });

  it('Webhook 测试样例自动展开为请求正文可用字段', () => {
    const schema = commonTriggerInputSchema({
      trigger_nodes: [{
        id: 'hook', name: 'Webhook', trigger_type: 'WEBHOOK',
        input_schema: {
          type: 'object',
          properties: { body: { type: 'object', title: '请求正文', properties: {}, additionalProperties: true } },
          required: ['body'],
          additionalProperties: false,
        },
        config: { response_mode: 'IMMEDIATE' },
      }],
      node_test_data: { hook: { body: { host: '10.0.0.8', severity: 'critical' } } },
    });

    expect(schema.properties?.body.properties).toEqual({
      host: { type: 'string', title: 'host' },
      severity: { type: 'string', title: 'severity' },
    });
  });

  it('画布以 Form 触发器作为默认入口', () => {
    const flow = buildWorkflowFlow(definition);

    expect(flow.nodes[0]).toMatchObject({
      id: 'trigger_form',
      data: { kind: 'trigger', title: '表单触发器', triggerType: 'FORM' },
    });
    expect(flow.edges.some((edge) => edge.source === 'trigger_form' && edge.target === 'first')).toBe(true);
  });

  it('显式空草稿不生成兼容旧数据的默认触发器', () => {
    const flow = buildWorkflowFlow({ ...definition, tasks: [] }, {
      trigger_nodes: [],
      return_nodes: [],
      edges: [],
    });

    expect(flow.nodes).toEqual([]);
    expect(flow.edges).toEqual([]);
  });

  it('健康巡检默认布局只展示作业执行与文档生成', () => {
    const healthDefinition: ConductorDefinition = {
      ...definition,
      tasks: [
        { name: 'bklite_job_execute', taskReferenceName: 'scan', type: 'SIMPLE', inputParameters: {} },
        { name: 'bklite_document_render', taskReferenceName: 'report', type: 'SIMPLE', inputParameters: {} },
      ],
    };

    const flow = buildWorkflowFlow(healthDefinition, { return_nodes: [] });
    expect(flow.nodes.map((node) => node.id)).toEqual(['trigger_form', 'scan', 'report']);
    expect(flow.nodes.slice(1).map((node) => node.position)).toEqual([
      { x: 260, y: 260 },
      { x: 480, y: 260 },
    ]);
    expect(flow.edges.map(({ source, target }) => [source, target])).toEqual([
      ['trigger_form', 'scan'],
      ['scan', 'report'],
    ]);
  });

  it('可同时展示多个触发器和 Webhook 响应节点', () => {
    const flow = buildWorkflowFlow(definition, {
      trigger_nodes: [
        { id: 'form', name: '表单', trigger_type: 'FORM', input_schema: {}, config: {} },
        { id: 'hook', name: 'Webhook', trigger_type: 'WEBHOOK', input_schema: {}, config: { response_mode: 'WAIT' } },
      ],
      return_nodes: [{ id: 'webhook_return', name: 'Webhook 响应', return_type: 'WEBHOOK', config: {} }],
    });
    expect(flow.nodes.filter((node) => node.data.kind === 'trigger')).toHaveLength(2);
    expect(flow.nodes.at(-1)?.data.kind).toBe('return');
  });

  it('不展示后端编译产生的并行和汇聚节点', () => {
    const structured: ConductorDefinition = {
      ...definition,
      tasks: [
        {
          name: '__auto_parallel', taskReferenceName: '__auto_fork_first', type: 'FORK_JOIN',
          forkTasks: [[definition.tasks[0]], [definition.tasks[1]]],
        },
        { name: '__auto_join', taskReferenceName: '__auto_join_first', type: 'JOIN', joinOn: ['first', 'second'] },
        definition.tasks[2],
      ],
    };

    expect(buildWorkflowFlow(structured).nodes.map((node) => node.id)).toEqual(['trigger_form', 'first', 'second', 'third']);
  });

  it('分支实例可使用业务名称和显式位置，避免多个同类原子看起来像重复串联', () => {
    const branched: ConductorDefinition = {
      ...definition,
      tasks: [{
        name: 'approval_decision', taskReferenceName: 'decision', type: 'SWITCH', inputParameters: {},
        decisionCases: {
          true: [{ name: 'bklite_notification', taskReferenceName: 'approved_path', type: 'SIMPLE', inputParameters: {} }],
          false: [{ name: 'bklite_notification', taskReferenceName: 'rejected_path', type: 'SIMPLE', inputParameters: {} }],
        },
        defaultCase: [],
      }],
    };
    const flow = buildWorkflowFlow(branched, {
      node_titles: { approved_path: '记录审批通过结果', rejected_path: '记录审批驳回结果' },
      positions: { approved_path: { x: 700, y: 160 }, rejected_path: { x: 700, y: 360 } },
    }, { bklite_notification: '对外通知' });

    expect(flow.nodes.find((node) => node.id === 'approved_path')).toMatchObject({
      position: { x: 700, y: 160 }, data: { title: '记录审批通过结果' },
    });
    expect(flow.nodes.find((node) => node.id === 'rejected_path')).toMatchObject({
      position: { x: 700, y: 360 }, data: { title: '记录审批驳回结果' },
    });
  });

  it('人工审批在画布折叠内部 SWITCH，直接暴露通过与驳回两个出口', () => {
    const approvalDefinition: ConductorDefinition = {
      ...definition,
      tasks: [
        {
          name: 'manual_approval', taskReferenceName: 'approve_change', type: 'HUMAN',
          inputParameters: { interactionType: 'APPROVAL', title: '生产变更审批', candidates: ['admin'] },
        },
        {
          name: 'approval_decision', taskReferenceName: 'approval_decision', type: 'SWITCH',
          inputParameters: { decision: '${approve_change.output.approved}' },
          decisionCases: { true: [], false: [] }, defaultCase: [],
        },
        { name: 'bklite_notification', taskReferenceName: 'notify_approved', type: 'SIMPLE', inputParameters: {} },
        { name: 'bklite_notification', taskReferenceName: 'notify_rejected', type: 'SIMPLE', inputParameters: {} },
      ],
    };
    const persistedEdges = [
      { id: 'start-approval', source: 'trigger_form', target: 'approve_change' },
      { id: 'approval-decision', source: 'approve_change', target: 'approval_decision' },
      { id: 'decision-approved', source: 'approval_decision', sourceHandle: 'true', target: 'notify_approved' },
      { id: 'decision-rejected', source: 'approval_decision', sourceHandle: 'false', target: 'notify_rejected' },
    ];

    const flow = buildWorkflowFlow(approvalDefinition, { edges: persistedEdges });

    expect(flow.nodes.map((node) => node.id)).toEqual(['trigger_form', 'approve_change', 'notify_approved', 'notify_rejected']);
    expect(flow.nodes.find((node) => node.id === 'approve_change')?.data.branches).toEqual([
      { id: 'true', label: '通过' },
      { id: 'false', label: '驳回' },
    ]);
    expect(flow.edges).toEqual([
      expect.objectContaining({ source: 'trigger_form', target: 'approve_change' }),
      expect.objectContaining({ source: 'approve_change', sourceHandle: 'true', target: 'notify_approved' }),
      expect.objectContaining({ source: 'approve_change', sourceHandle: 'false', target: 'notify_rejected' }),
    ]);
    expect(expandApprovalCanvasEdges(approvalDefinition, flow.edges)).toEqual([
      expect.objectContaining({ source: 'trigger_form', target: 'approve_change' }),
      expect.objectContaining({ source: 'approval_decision', sourceHandle: 'true', target: 'notify_approved' }),
      expect.objectContaining({ source: 'approval_decision', sourceHandle: 'false', target: 'notify_rejected' }),
      expect.objectContaining({ source: 'approve_change', target: 'approval_decision' }),
    ]);
  });

  it('条件分支是布尔 SWITCH，出口文案为满足/不满足而不是审批通过/驳回', () => {
    const conditionDefinition: ConductorDefinition = {
      ...definition,
      tasks: [{
        name: 'condition',
        taskReferenceName: 'condition',
        type: 'SWITCH',
        decisionCases: { true: [], false: [] },
        defaultCase: [],
      }],
    };

    const flow = buildWorkflowFlow(conditionDefinition, {
      node_titles: { condition: '条件分支' },
    });

    expect(flow.nodes.find((node) => node.id === 'condition')).toMatchObject({
      data: {
        title: '条件分支',
        taskType: 'SWITCH',
        branches: [
          { id: 'true', label: '满足' },
          { id: 'false', label: '不满足' },
        ],
      },
    });
  });
});
