import { describe, expect, it } from 'vitest';
import { canvasFromDesign, designFromCanvas, type FlowDesign } from './demo-flow';

describe('流程配置往返', () => {
  it('编辑画布不丢失字段权限和自动节点配置', () => {
    const design: FlowDesign = { nodes: [
      { id: 'approval_1', type: 'approval', name: '审批', field_perm: { secret: 'read' }, actions: ['approve', 'reject'] },
      { id: 'auto_1', type: 'auto', name: '写表', auto: { kind: 'table', table_key: 'result' } },
    ], edges: [{ from: 'approval_1', to: 'auto_1' }] };
    const canvas = canvasFromDesign(design);
    expect(designFromCanvas(canvas.nodes, canvas.edges)).toEqual(design);
  });
});
