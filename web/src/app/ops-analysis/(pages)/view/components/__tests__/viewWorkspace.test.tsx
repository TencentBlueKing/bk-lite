import React from 'react';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/components/ellipsis-with-tooltip', () => ({
  default: ({ text }: { text: string }) => <span>{text}</span>,
}));

vi.mock('@/components/source-origin-badge', () => ({
  default: () => <span>内置</span>,
}));

vi.mock('@/app/ops-analysis/utils/canvasDescription', () => ({
  resolveCanvasDescription: (desc?: string) => desc?.trim() || '',
}));

import ViewWorkspace from '../viewWorkspace';

afterEach(() => {
  cleanup();
});

const item = {
  id: '1',
  data_id: '106',
  name: '运维总览',
  desc: '这是一段描述',
  type: 'dashboard' as const,
  is_build_in: true,
};

describe('ViewWorkspace compactHeader', () => {
  it('drops the dashboard title row and any homepage toolbar', () => {
    const { container } = render(
      <ViewWorkspace
        selectedItem={item}
        titleFallback="仪表盘"
        emptyDescription="空"
        compactHeader
        toolbar={<a href="/ops">在运营分析中打开</a>}
      >
        <div>canvas</div>
      </ViewWorkspace>
    );

    expect(screen.queryByRole('heading', { name: '运维总览' })).toBeNull();
    expect(screen.queryByText('运维总览')).toBeNull();
    expect(screen.queryByText('仪表盘')).toBeNull();
    expect(screen.queryByText('在运营分析中打开')).toBeNull();
    expect(container.querySelector('.border-b')).toBeNull();
    expect(screen.queryByText('这是一段描述')).toBeNull();
    expect(screen.queryByText('内置')).toBeNull();
    expect(screen.getByText('canvas')).toBeTruthy();
  });

  it('keeps title, description and badge in the default header', () => {
    render(
      <ViewWorkspace
        selectedItem={item}
        titleFallback="仪表盘"
        emptyDescription="空"
        toolbar={<a href="/ops">在运营分析中打开</a>}
      >
        <div>canvas</div>
      </ViewWorkspace>
    );

    expect(screen.getByRole('heading', { name: '运维总览' })).toBeTruthy();
    expect(screen.getByRole('link', { name: '在运营分析中打开' })).toBeTruthy();
    expect(screen.getByText('这是一段描述')).toBeTruthy();
    expect(screen.getByText('内置')).toBeTruthy();
  });
});
