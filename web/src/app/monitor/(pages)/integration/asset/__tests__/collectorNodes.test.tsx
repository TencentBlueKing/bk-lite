import React from 'react';
import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  CollectorNodeColumn,
  collectorNodeDetailText,
  summarizeInstanceCollectorNodes,
} from '../collectorNodes';

afterEach(cleanup);

beforeEach(() => {
  window.matchMedia = vi.fn().mockReturnValue({
    matches: false,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  });
});

describe('summarizeInstanceCollectorNodes', () => {
  it('汇总各采集方式的节点，并按节点 ID 去重', () => {
    expect(
      summarizeInstanceCollectorNodes([
        {
          collector_nodes: [
            { id: 'node-2', name: 'Beta', active: true },
            { id: 'node-1', name: 'Alpha', active: true },
          ],
        },
        {
          collector_nodes: [
            { id: 'node-1', name: 'Alpha duplicate', active: true },
            { id: 'node-3', name: 'Gamma', active: true },
          ],
        },
      ])
    ).toEqual([
      { id: 'node-1', name: 'Alpha', state: 'online' },
      { id: 'node-2', name: 'Beta', state: 'online' },
      { id: 'node-3', name: 'Gamma', state: 'online' },
    ]);
  });

  it('active 为 false 且未删除时记为离线', () => {
    expect(
      summarizeInstanceCollectorNodes([
        { collector_nodes: [{ id: 'node-1', name: 'Alpha', active: false }] },
      ])
    ).toEqual([{ id: 'node-1', name: 'Alpha', state: 'offline' }]);
  });

  it('已删除快照优先于离线标记', () => {
    expect(
      summarizeInstanceCollectorNodes([
        {
          collector_nodes: [
            { id: 'node-1', name: 'Alpha', removed: true, active: false },
          ],
        },
      ])
    ).toEqual([{ id: 'node-1', name: 'Alpha', state: 'removed' }]);
  });

  it('缺省 active 不能把明确离线盖成在线，明确在线优先于离线', () => {
    expect(
      summarizeInstanceCollectorNodes([
        { collector_nodes: [{ id: 'node-1', name: 'Alpha', active: false }] },
        { collector_nodes: [{ id: 'node-1', name: 'Alpha later' }] },
      ])
    ).toEqual([{ id: 'node-1', name: 'Alpha', state: 'offline' }]);

    expect(
      summarizeInstanceCollectorNodes([
        { collector_nodes: [{ id: 'node-2', name: 'Beta', active: false }] },
        { collector_nodes: [{ id: 'node-2', name: 'Beta', active: true }] },
      ])
    ).toEqual([{ id: 'node-2', name: 'Beta', state: 'online' }]);
  });

  it('同一节点仍有存活记录时，不采用已删除快照', () => {
    expect(
      summarizeInstanceCollectorNodes([
        {
          collector_nodes: [
            { id: 'node-1', name: 'Old', removed: true, active: false },
          ],
        },
        {
          collector_nodes: [{ id: 'node-1', name: 'Alpha', active: false }],
        },
      ])
    ).toEqual([{ id: 'node-1', name: 'Alpha', state: 'offline' }]);
  });

  it('缺少 active 且未删除时显示为在线', () => {
    expect(
      summarizeInstanceCollectorNodes([
        { collector_nodes: [{ id: 'node-1', name: '' }] },
        { collector_nodes: [{ id: '  ', name: 'Blank' }] },
      ])
    ).toEqual([{ id: 'node-1', name: 'node-1', state: 'online' }]);
  });

  it('没有节点时返回空列表', () => {
    expect(summarizeInstanceCollectorNodes(undefined)).toEqual([]);
    expect(summarizeInstanceCollectorNodes([{ collector_nodes: [] }])).toEqual(
      []
    );
  });
});

describe('collectorNodeDetailText', () => {
  const labels = { offline: '离线', removed: '采集节点已删除' };

  it('在线只保留名称和 ID', () => {
    expect(
      collectorNodeDetailText(
        { id: 'node-1', name: 'Alpha', state: 'online' },
        labels
      )
    ).toBe('Alpha (node-1)');
  });

  it('离线和已删除附在名称后面', () => {
    expect(
      collectorNodeDetailText(
        { id: 'node-1', name: 'Alpha', state: 'offline' },
        labels
      )
    ).toBe('Alpha (node-1) · 离线');
    expect(
      collectorNodeDetailText(
        { id: 'node-1', name: 'node-1', state: 'removed' },
        labels
      )
    ).toBe('node-1 · 采集节点已删除');
  });
});

describe('CollectorNodeColumn', () => {
  const labels = {
    notAssociatedText: '未关联',
    offlineText: '离线',
    removedText: '采集节点已删除',
  };

  it('无节点时显示未关联', () => {
    render(<CollectorNodeColumn plugins={[]} {...labels} />);
    expect(screen.getByText('未关联')).not.toBeNull();
  });

  it('单个在线节点只显示名称', () => {
    render(
      <CollectorNodeColumn
        plugins={[
          { collector_nodes: [{ id: 'node-1', name: 'Alpha', active: true }] },
        ]}
        {...labels}
      />
    );
    expect(screen.getByText('Alpha')).not.toBeNull();
    expect(screen.queryByText('离线')).toBeNull();
    expect(screen.queryByText('采集节点已删除')).toBeNull();
  });

  it('离线、已删除和多个节点一起展示', async () => {
    const user = userEvent.setup();
    render(
      <CollectorNodeColumn
        plugins={[
          {
            collector_nodes: [
              { id: 'node-1', name: 'Alpha', active: true },
              { id: 'node-2', name: 'Beta', active: false },
            ],
          },
          {
            collector_nodes: [
              { id: 'node-3', name: 'Gone', removed: true },
            ],
          },
        ]}
        {...labels}
      />
    );

    expect(screen.getByText('Alpha')).not.toBeNull();
    expect(screen.getByText('Beta')).not.toBeNull();
    expect(screen.getByText('Gone')).not.toBeNull();
    expect(screen.getByText('离线')).not.toBeNull();
    expect(screen.getByText('采集节点已删除')).not.toBeNull();

    await user.hover(screen.getByText('Beta'));
    expect(await screen.findByText('Beta (node-2) · 离线')).toBeTruthy();
  });
});
