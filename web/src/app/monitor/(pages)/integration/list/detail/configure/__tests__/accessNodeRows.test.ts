import { describe, expect, it } from 'vitest';
import {
  applyNodeIdToEmptyRows,
  buildAgentRowsFromNodes,
  listUnusedAgentNodes,
} from '../accessNodeRows';

describe('applyNodeIdToEmptyRows', () => {
  it('fills empty node cells and keeps already chosen nodes', () => {
    const rows = [
      { key: '1', node_ids: 'proxy-a', host: '10.0.0.1' },
      { key: '2', node_ids: null, host: '10.0.0.2' },
      { key: '3', node_ids: 'keep', host: '10.0.0.3' },
    ];
    const filled = applyNodeIdToEmptyRows(rows, 'proxy-a');
    expect(filled[0].node_ids).toBe('proxy-a');
    expect(filled[1].node_ids).toBe('proxy-a');
    expect(filled[2].node_ids).toBe('keep');
  });

  it('does nothing when the source node is empty', () => {
    const rows = [{ key: '1', node_ids: null }];
    expect(applyNodeIdToEmptyRows(rows, null)).toBe(rows);
  });
});

describe('listUnusedAgentNodes', () => {
  const nodes = [
    { id: 'n1', value: 'n1', name: 'agent-1', disabled: false },
    { id: 'n2', value: 'n2', name: 'agent-2', disabled: true },
    { id: 'n3', value: 'n3', name: 'box', node_type: 'container' },
    { id: 'n4', value: 'n4', name: 'agent-4', disabled: false },
    { id: 'n4-dup', value: 'n4', name: 'agent-4-dup', disabled: false },
  ];

  it('skips configured, container, and already selected nodes', () => {
    const unused = listUnusedAgentNodes(nodes, [{ key: '1', node_ids: 'n1' }]);
    expect(unused.map((node) => node.value)).toEqual(['n4']);
  });
});

describe('buildAgentRowsFromNodes', () => {
  it('creates rows with node id and instance name', () => {
    const rows = buildAgentRowsFromNodes(
      [{ id: 'n4', value: 'n4', name: 'host-4' }],
      { group_ids: ['1'], instance_name: null },
      () => 'k-1',
    );
    expect(rows).toEqual([
      {
        group_ids: ['1'],
        instance_name: 'host-4',
        key: 'k-1',
        node_ids: 'n4',
        node_ids_error: null,
        instance_name_error: null,
      },
    ]);
  });
});
