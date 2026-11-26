import { expect, it } from 'vitest';
import { canvasFromDesign, designFromCanvas, type FlowDesign } from '../constants/demo-flow';
it('清空处理人和操作按钮必须持久化，不恢复旧值', () => {
  const graph=canvasFromDesign({nodes:[{id:'a',type:'handle',name:'处理',assignee:{source:'users',value:['old']},actions:['submit']}],edges:[]});
  graph.nodes[0].data.assignees=[]; graph.nodes[0].data.actions=[];
  const node=designFromCanvas(graph.nodes,[]).nodes[0];
  expect(node.assignee?.value).toEqual([]); expect(node.actions).toEqual([]);
});
it('表单引用处理人往返保存不变', () => {
  const design={nodes:[{id:'a',type:'handle',name:'处理',assignee:{source:'variable',value:'form.owner'}}],edges:[]};
  const graph=canvasFromDesign(design); expect(designFromCanvas(graph.nodes,[]).nodes[0].assignee).toEqual(design.nodes[0].assignee);
});
it('转交范围随节点保存，切回不限时清除旧范围', () => {
  const design: FlowDesign = {
    nodes: [{ id: 'handler', type: 'handle', name: '处理', transfer_scope: { type: 'users', users: ['alice'] } }],
    edges: [],
  };
  const graph = canvasFromDesign(design);
  expect(designFromCanvas(graph.nodes, []).nodes[0].transfer_scope).toEqual(design.nodes[0].transfer_scope);
  graph.nodes[0].data.transferScope = { type: 'handler_groups', group_ids: [7] };
  expect(designFromCanvas(graph.nodes, []).nodes[0].transfer_scope).toEqual({ type: 'handler_groups', group_ids: [7] });
  graph.nodes[0].data.transferScope = null;
  expect(designFromCanvas(graph.nodes, []).nodes[0].transfer_scope).toBeUndefined();
  const legacy = canvasFromDesign({ nodes: [{ id: 'legacy', type: 'handle', name: '旧节点' }], edges: [] });
  expect(designFromCanvas(legacy.nodes, []).nodes[0].transfer_scope).toBeUndefined();
});

it('节点的必填意见按钮往返保存，清空后不会恢复旧配置', () => {
  const design: FlowDesign = {
    nodes: [{ id: 'approval', type: 'approval', name: '审批', required_opinion_actions: ['approve'] }],
    edges: [],
  };
  const graph = canvasFromDesign(design);
  expect(graph.nodes[0].data.requiredOpinionActions).toEqual(['approve']);
  expect(designFromCanvas(graph.nodes, []).nodes[0].required_opinion_actions).toEqual(['approve']);
  graph.nodes[0].data.requiredOpinionActions = [];
  expect(designFromCanvas(graph.nodes, []).nodes[0].required_opinion_actions).toEqual([]);
});

it('发布草稿保存按钮顺序及名称，保留隐式启用规则', () => {
  const design: FlowDesign = { nodes: [{ id: 'approval', type: 'approval', name: '审批',
    action_display: [{ action: 'approve', label: '批准申请' }, { action: 'reject' }],
  }], edges: [] };
  const graph = canvasFromDesign(design);
  expect(graph.nodes[0].data.actionDisplay).toEqual(design.nodes[0].action_display);
  graph.nodes[0].data.actionDisplay = [{ action: 'reject' }, { action: 'approve', label: '验收通过' }];
  expect(designFromCanvas(graph.nodes, []).nodes[0]).toEqual({ ...design.nodes[0],
    action_display: [{ action: 'reject' }, { action: 'approve', label: '验收通过' }],
  });
});

it('引用服务处理组的节点能新增并往返保存，无需指定固定组 ID', () => {
  const graph = canvasFromDesign({ nodes: [{ id: 'approve', type: 'approval', name: '分派' }], edges: [] });
  graph.nodes[0].data.assigneeSource = 'service_group';
  const result = designFromCanvas(graph.nodes, []);
  expect(result.nodes[0].assignee).toEqual({ source: 'service_group', value: [] });
  expect(designFromCanvas(canvasFromDesign(result).nodes, []).nodes[0].assignee).toEqual(result.nodes[0].assignee);
});
