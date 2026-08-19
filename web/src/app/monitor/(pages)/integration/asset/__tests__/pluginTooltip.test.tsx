import React from 'react';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';

import PluginTooltipContent, {
  formatCollectorNodes,
} from '../pluginTooltip';

afterEach(cleanup);

describe('formatCollectorNodes', () => {
  it('formats one node with stable id and name', () => {
    expect(
      formatCollectorNodes('auto', [{ id: 'node-1', name: 'Alpha' }])
    ).toEqual(['Alpha (node-1)']);
  });

  it('formats multiple nodes and removes duplicate ids', () => {
    expect(
      formatCollectorNodes('auto', [
        { id: 'node-1', name: 'Alpha' },
        { id: 'node-2', name: 'Beta' },
        { id: 'node-1', name: 'Duplicate' },
      ])
    ).toEqual(['Alpha (node-1)', 'Beta (node-2)']);
  });

  it.each([
    ['auto', []],
    ['manual', [{ id: 'node-1', name: 'Alpha' }]],
  ])('returns no nodes for %s collection without a binding', (mode, nodes) => {
    expect(formatCollectorNodes(mode, nodes)).toEqual([]);
  });
});

describe('PluginTooltipContent', () => {
  it('renders status, report time and multiple collection nodes', () => {
    render(
      <PluginTooltipContent
        statusText="正常"
        lastReportTimeLabel="最后上报时间"
        timeText="2026-08-19 10:00"
        collectionNodeLabel="采集节点"
        notAssociatedText="未关联"
        collectMode="auto"
        collectorNodes={[
          { id: 'node-1', name: 'Alpha' },
          { id: 'node-2', name: 'Beta' },
        ]}
      />
    );

    expect(screen.getByText('正常')).not.toBeNull();
    expect(screen.getByText('最后上报时间：2026-08-19 10:00')).not.toBeNull();
    expect(screen.getByText('Alpha (node-1)')).not.toBeNull();
    expect(screen.getByText('Beta (node-2)')).not.toBeNull();
  });

  it('renders a clear unassociated state for manual reporting', () => {
    render(
      <PluginTooltipContent
        statusText="正常"
        lastReportTimeLabel="最后上报时间"
        timeText="--"
        collectionNodeLabel="采集节点"
        notAssociatedText="未关联"
        collectMode="manual"
        collectorNodes={[{ id: 'node-1', name: 'Alpha' }]}
      />
    );

    expect(screen.getByText('未关联')).not.toBeNull();
    expect(screen.queryByText('Alpha (node-1)')).toBeNull();
  });
});
