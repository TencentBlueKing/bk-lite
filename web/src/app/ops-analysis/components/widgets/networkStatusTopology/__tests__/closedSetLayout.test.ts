import { describe, expect, it, vi } from 'vitest';

vi.mock('@/app/cmdb/components/networkTopology', () => ({
  layoutNetworkTopology: ({
    nodes,
    links,
  }: {
    nodes: Array<{ id: string }>;
    links?: Array<{ id: string }>;
  }) => ({
    nodes: nodes.map((node, index) => ({ ...node, x: index * 200, y: 0 })),
    links: links || [],
  }),
}));

import {
  packClosedSetLayout,
  splitClosedSetComponents,
} from '../closedSetLayout';

describe('closedSetLayout', () => {
  it('keeps linked groups and degree-zero islands', () => {
    const split = splitClosedSetComponents(
      ['a', 'b', 'c', 'd'],
      [
        { source: 'a', target: 'b' },
        { source: 'c', target: 'a' },
      ],
    );
    expect(split.isolated).toEqual(['d']);
    expect(split.components).toHaveLength(1);
    expect([...split.components[0]].sort()).toEqual(['a', 'b', 'c']);
  });

  it('parks islands to the right of connected nodes', () => {
    const result = packClosedSetLayout({
      mode: 'hierarchical',
      nodes: [
        { id: 'a', modelId: 'switch', name: 'A' },
        { id: 'b', modelId: 'switch', name: 'B' },
        { id: 'island', modelId: 'router', name: 'Island' },
      ],
      links: [{ id: 'ab', source: 'a', target: 'b' }],
    });
    const byId = new Map(result.nodes.map((node) => [node.id, node]));
    const island = byId.get('island');
    const connected = result.nodes.filter((node) => node.id !== 'island');
    expect(island).toBeTruthy();
    const maxConnectedX = Math.max(...connected.map((node) => node.x));
    expect(island!.x).toBeGreaterThan(maxConnectedX);
  });
});
