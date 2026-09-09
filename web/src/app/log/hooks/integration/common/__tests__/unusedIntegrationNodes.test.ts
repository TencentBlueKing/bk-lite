import { describe, expect, it } from 'vitest';
import { unusedIntegrationNodes } from '../unusedIntegrationNodes';

describe('unusedIntegrationNodes', () => {
  it('keeps the current row node and hides nodes already used by other rows', () => {
    const unused = unusedIntegrationNodes(
      [
        { node_ids: 'node-a' },
        { node_ids: 'node-b' },
      ],
      [
        { id: 'node-a', name: 'A' },
        { id: 'node-b', name: 'B' },
        { id: 'node-c', name: 'C' },
      ],
      'node-a'
    );

    expect(unused.map((item) => item.id)).toEqual(['node-a', 'node-c']);
  });
});
