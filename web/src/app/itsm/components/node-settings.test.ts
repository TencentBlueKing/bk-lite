import { expect, it } from 'vitest';
import { canvasFromDesign, designFromCanvas } from '../constants/demo-flow';
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
