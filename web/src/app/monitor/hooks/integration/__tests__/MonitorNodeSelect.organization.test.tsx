import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import React from 'react';
import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  buildMonitorNodeCacheScope,
  clearMonitorNodeQueryCaches,
} from '../fetchMonitorNodePages';
import MonitorNodeSelect from '../MonitorNodeSelect';

function node(id: string, label: string) {
  return { id, value: id, label };
}

function AccessNodeSelect({
  organizationId,
  includeChildren = false,
  loadNodes,
}: {
  organizationId: string;
  includeChildren?: boolean;
  loadNodes: (query: { page: number; pageSize: number; keyword: string }) => Promise<{
    count: number;
    nodes: ReturnType<typeof node>[];
  }>;
}) {
  return (
    <MonitorNodeSelect
      cacheScope={buildMonitorNodeCacheScope('42', organizationId, includeChildren)}
      loadNodes={loadNodes}
    />
  );
}

async function openNodeList() {
  const user = userEvent.setup();
  await user.click(screen.getByRole('combobox'));
}

describe('接入监控实例的节点列表', () => {
  beforeEach(() => {
    clearMonitorNodeQueryCaches();
  });

  afterEach(() => {
    cleanup();
    clearMonitorNodeQueryCaches();
  });

  it('切换组织后再次打开同一插件，展示新组织的节点', async () => {
    const loadPreviousOrganization = vi.fn(async () => ({
      count: 1,
      nodes: [node('node-old', '旧组织节点')],
    }));
    const previous = render(
      <AccessNodeSelect organizationId="org-old" loadNodes={loadPreviousOrganization} />
    );

    await openNodeList();
    expect(await screen.findByText('旧组织节点')).toBeTruthy();
    expect(loadPreviousOrganization).toHaveBeenCalledTimes(1);
    previous.unmount();

    const loadCurrentOrganization = vi.fn(async () => ({
      count: 1,
      nodes: [node('node-new', '新组织节点')],
    }));
    render(
      <AccessNodeSelect organizationId="org-new" loadNodes={loadCurrentOrganization} />
    );

    await openNodeList();
    expect(await screen.findByText('新组织节点')).toBeTruthy();
    expect(screen.queryByText('旧组织节点')).toBeNull();
    expect(loadCurrentOrganization).toHaveBeenCalledTimes(1);
  });

  it('同一组织再次打开时继续复用已加载的节点', async () => {
    const loadNodes = vi.fn(async () => ({
      count: 1,
      nodes: [node('node-current', '本组织节点')],
    }));
    const first = render(
      <AccessNodeSelect organizationId="org-current" loadNodes={loadNodes} />
    );
    await openNodeList();
    expect(await screen.findByText('本组织节点')).toBeTruthy();
    first.unmount();

    render(<AccessNodeSelect organizationId="org-current" loadNodes={loadNodes} />);
    await openNodeList();
    expect(await screen.findByText('本组织节点')).toBeTruthy();
    expect(loadNodes).toHaveBeenCalledTimes(1);
  });

  it('接入页按当前组织和子组织范围区分节点缓存', () => {
    const source = readFileSync(
      path.resolve(
        path.dirname(fileURLToPath(import.meta.url)),
        '../../../(pages)/integration/list/detail/configure/automatic.tsx',
      ),
      'utf8',
    );

    expect(buildMonitorNodeCacheScope('42', 'org-old')).not.toBe(
      buildMonitorNodeCacheScope('42', 'org-new'),
    );
    expect(buildMonitorNodeCacheScope('42', 'org-current', false)).not.toBe(
      buildMonitorNodeCacheScope('42', 'org-current', true),
    );
    expect(source).toContain('buildMonitorNodeCacheScope(');
    expect(source).toContain('userContext?.selectedGroup?.id');
    expect(source).toContain("Cookies.get('include_children') === '1'");
    expect(source).not.toContain("monitorNodeCacheScope: String(pluginId || 'default')");
  });
});
