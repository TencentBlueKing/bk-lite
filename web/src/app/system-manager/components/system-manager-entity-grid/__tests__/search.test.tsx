import React from 'react';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import SystemManagerEntityGrid from '@/app/system-manager/components/system-manager-entity-grid';

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock('@/components/compact-empty-state', () => ({
  default: ({ description }: { description?: string }) => <div>{description}</div>,
}));

afterEach(() => {
  cleanup();
});

const items = [
  { id: 1, name: 'AD目录测试' },
  { id: 2, name: '企微测试' },
  { id: 3, name: '飞书' },
];

function renderGrid() {
  return render(
    <SystemManagerEntityGrid
      title="用户同步"
      description="接入主身份数据"
      items={items}
      getItemKey={(item) => item.id}
      renderCard={(item) => <article>{item.name}</article>}
    />,
  );
}

describe('SystemManagerEntityGrid search', () => {
  it('keeps title and description on the same row as search', () => {
    renderGrid();

    expect(screen.getByText('用户同步')).toBeTruthy();
    expect(screen.getByText('接入主身份数据')).toBeTruthy();
    expect(screen.getByRole('searchbox')).toBeTruthy();
  });

  it('filters cards by name when the search button is clicked', () => {
    renderGrid();

    fireEvent.change(screen.getByRole('searchbox'), { target: { value: '企微' } });
    fireEvent.click(screen.getByRole('button', { name: 'search' }));

    expect(screen.getByText('企微测试')).toBeTruthy();
    expect(screen.queryByText('AD目录测试')).toBeNull();
    expect(screen.queryByText('飞书')).toBeNull();
  });

  it('shows empty state when no card name matches', () => {
    renderGrid();

    fireEvent.change(screen.getByRole('searchbox'), { target: { value: '1' } });
    fireEvent.click(screen.getByRole('button', { name: 'search' }));

    expect(screen.getByText('common.noData')).toBeTruthy();
    expect(screen.queryByText('企微测试')).toBeNull();
  });
});
