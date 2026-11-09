'use client';

import { Background, ReactFlow } from '@xyflow/react';
import '@xyflow/react/dist/style.css';

const nodes = [
  { id: 'start', position: { x: 0, y: 0 }, data: { label: '开始' } },
  { id: 'submit', position: { x: 180, y: 0 }, data: { label: '提单' } },
  { id: 'approve_1', position: { x: 360, y: 0 }, data: { label: '部门审批' } },
  { id: 'end', position: { x: 540, y: 0 }, data: { label: '结束' } },
];
const edges = [
  { id: 'a', source: 'start', target: 'submit' },
  { id: 'b', source: 'submit', target: 'approve_1' },
  { id: 'c', source: 'approve_1', target: 'end' },
];

export function FlowDesigner() {
  return (
    <div style={{ height: 480 }}>
      <ReactFlow nodes={nodes} edges={edges} fitView>
        <Background />
      </ReactFlow>
    </div>
  );
}
