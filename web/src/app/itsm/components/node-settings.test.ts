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
