import { describe, expect, it } from 'vitest';

import { layoutWorkflowCanvas } from '../lib/canvas-layout';

describe('流程画布整理', () => {
  it('按依赖关系排列分支和汇聚节点，而不是把所有节点平铺成一行', async () => {
    const nodes = [
      { id: 'trigger', position: { x: 0, y: 100 } },
      { id: 'fork', position: { x: 200, y: 100 } },
      { id: 'linux', position: { x: 400, y: 0 } },
      { id: 'windows', position: { x: 400, y: 200 } },
      { id: 'join', position: { x: 600, y: 100 } },
      { id: 'report', position: { x: 800, y: 100 } },
    ];
    const edges = [
      { source: 'trigger', target: 'fork' },
      { source: 'fork', target: 'linux' },
      { source: 'fork', target: 'windows' },
      { source: 'linux', target: 'join' },
      { source: 'windows', target: 'join' },
      { source: 'join', target: 'report' },
    ];

    const result = await layoutWorkflowCanvas(nodes, edges);
    const byId = Object.fromEntries(result.map((node) => [node.id, node.position]));

    expect(byId.linux.x).toBe(byId.windows.x);
    expect(byId.linux.y).toBeLessThan(byId.windows.y);
    expect(byId.trigger.y).toBe(byId.fork.y);
    expect(byId.fork.y).toBe(byId.join.y);
    expect(byId.join.y).toBe(byId.report.y);
    expect(byId.trigger.x).toBeLessThan(byId.fork.x);
    expect(byId.fork.x).toBeLessThan(byId.linux.x);
    expect(byId.linux.x).toBeLessThan(byId.join.x);
  });

  it('把断开的子图分区纵向排列', async () => {
    const nodes = [
      { id: 'connected-a', position: { x: 0, y: 0 } },
      { id: 'connected-b', position: { x: 200, y: 0 } },
      { id: 'detached', position: { x: 0, y: 300 } },
    ];

    const result = await layoutWorkflowCanvas(nodes, [{ source: 'connected-a', target: 'connected-b' }]);
    const byId = Object.fromEntries(result.map((node) => [node.id, node.position]));

    expect(byId.detached.y).toBeGreaterThan(byId['connected-a'].y);
    expect(byId.detached.y - byId['connected-a'].y).toBeGreaterThanOrEqual(224);
  });
});
