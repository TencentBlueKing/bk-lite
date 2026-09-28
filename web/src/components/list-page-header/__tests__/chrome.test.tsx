import React from 'react';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';

import ListPageHeader from '@/components/list-page-header';
import CardGridSkeleton from '@/components/card-grid-skeleton';

afterEach(() => {
  cleanup();
});

describe('list page chrome', () => {
  it('keeps the title on the left and actions grouped on the right', () => {
    render(
      <ListPageHeader
        title="应用"
        description="管理系统应用入口。"
        actions={<button type="button">新建</button>}
      />,
    );

    expect(screen.getByText('应用')).toBeTruthy();
    expect(screen.getByText('管理系统应用入口。')).toBeTruthy();
    expect(screen.getByText('管理系统应用入口。').className).toContain('text-xs');
    expect(screen.getByText('管理系统应用入口。').className).toContain('line-clamp-2');
    expect(screen.getByRole('button', { name: '新建' })).toBeTruthy();
  });

  it('exposes a busy grid for Look B loading', () => {
    const { container } = render(<CardGridSkeleton count={2} />);
    expect((container.firstChild as HTMLElement).getAttribute('aria-busy')).toBe('true');
    expect(container.querySelectorAll('[class*="min-h-[168px]"]').length).toBe(2);
  });

  it('uses a compact skeleton without footer slots', () => {
    const { container } = render(<CardGridSkeleton count={2} compact />);
    expect(container.querySelectorAll('[class*="min-h-[144px]"]').length).toBe(2);
    expect(container.querySelectorAll('[class*="min-h-[168px]"]').length).toBe(0);
    expect(container.querySelectorAll('[class*="border-t"]').length).toBe(0);
  });
});
