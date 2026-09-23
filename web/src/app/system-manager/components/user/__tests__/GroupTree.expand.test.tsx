import React from 'react';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';

import GroupTree from '@/app/system-manager/components/user/GroupTree';
import type { ExtendedTreeDataNode } from '@/app/system-manager/utils/userTreeUtils';

vi.mock('@/hooks/usePermissions', () => ({
  default: () => ({ hasPermission: () => false }),
}));

vi.mock('@/components/icon', () => ({
  default: ({ type }: { type: string }) => <span data-testid={`icon-${type}`} />,
}));

vi.mock('@/components/ellipsis-with-tooltip', () => ({
  default: ({ text }: { text: React.ReactNode }) => <span>{text}</span>,
}));

vi.mock('@/components/more-actions-dropdown', () => ({
  default: () => <button type="button">more</button>,
}));

vi.mock('@/components/permission', () => ({
  default: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

const treeData: ExtendedTreeDataNode[] = [
  {
    key: 1,
    title: 'Default',
    children: [
      { key: 11, title: 'TestSubOrg' },
      {
        key: 12,
        title: 'Nested',
        children: [{ key: 121, title: 'Deep' }],
      },
    ],
  },
  {
    key: 2,
    title: 'Guest1',
    children: [{ key: 21, title: 'Guest child' }],
  },
  { key: 3, title: '本地根组织' },
];

beforeAll(() => {
  Object.defineProperty(HTMLElement.prototype, 'clientHeight', {
    configurable: true,
    get() {
      return 400;
    },
  });
  class ResizeObserverMock {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
  vi.stubGlobal('ResizeObserver', ResizeObserverMock);
});

afterEach(() => {
  cleanup();
});

describe('GroupTree default expansion', () => {
  it('expands every folder so the full tree is visible', () => {
    render(
      <GroupTree
        treeData={treeData}
        searchValue=""
        onSearchChange={() => undefined}
        onAddRootGroup={() => undefined}
        onTreeSelect={() => undefined}
        onGroupAction={() => undefined}
        t={(key) => key}
      />,
    );

    expect(screen.getByText('Default').closest('[role="treeitem"]')?.getAttribute('aria-expanded')).toBe('true');
    expect(screen.getByText('Guest1').closest('[role="treeitem"]')?.getAttribute('aria-expanded')).toBe('true');
    expect(screen.getByText('Nested').closest('[role="treeitem"]')?.getAttribute('aria-expanded')).toBe('true');
    expect(screen.getByText('TestSubOrg')).toBeTruthy();
    expect(screen.getByText('Guest child')).toBeTruthy();
    expect(screen.getByText('Deep')).toBeTruthy();
    expect(screen.getByText('本地根组织')).toBeTruthy();
    expect(document.querySelector('.ant-tree-show-line')).toBeTruthy();
    expect(document.querySelector('[data-icon="caret-down"]')).toBeTruthy();
    expect(document.querySelector('[data-icon="plus-square"]')).toBeNull();
  });

  it('keeps the more-actions button when a node title is very long', () => {
    const longTitle = 'weops产品weops产品weops产品weops产品weops产品weops产品';
    render(
      <GroupTree
        treeData={[
          {
            key: 1,
            title: longTitle,
            children: [{ key: 11, title: 'Child' }],
          },
        ]}
        searchValue=""
        onSearchChange={() => undefined}
        onAddRootGroup={() => undefined}
        onTreeSelect={() => undefined}
        onGroupAction={() => undefined}
        t={(key) => key}
      />,
    );

    const row = screen.getByText(longTitle).closest('[role="treeitem"]');
    expect(row?.querySelector('.min-w-0.overflow-hidden')).toBeTruthy();
    expect(row?.textContent).toContain('more');
  });
});
