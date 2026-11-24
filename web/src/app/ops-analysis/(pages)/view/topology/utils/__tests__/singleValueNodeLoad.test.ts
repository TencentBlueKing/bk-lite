import { describe, expect, it } from 'vitest';
import { createNodeByType } from '../registerNode';

describe('single-value node initial load state', () => {
  it('starts a count-only node in the loading state', () => {
    const created = createNodeByType({
      id: 'node-count',
      type: 'single-value',
      name: '主机数',
      valueConfig: {
        dataSource: 209,
        selectedFields: [],
        scalarCalc: { method: 'count' },
      },
    });

    expect(created.data?.isLoading).toBe(true);
    expect(created.attrs?.label?.text).toBe('loading');
  });

  it('keeps a node without a source on the empty mark', () => {
    const created = createNodeByType({
      id: 'node-empty',
      type: 'single-value',
      name: '空',
      valueConfig: {
        selectedFields: [],
      },
    });

    expect(created.data?.isLoading).toBe(false);
    expect(created.attrs?.label?.text).toBe('--');
  });
});
