import React from 'react';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';

import TopSection from '@/components/top-section';

afterEach(() => {
  cleanup();
});

describe('TopSection', () => {
  it('keeps the title and a two-line description without a fixed bar height', () => {
    const { container } = render(
      <TopSection title="组织架构" content="维护组织与用户，并分配角色。" />,
    );

    const bar = container.firstChild as HTMLElement;
    expect(bar.className).not.toContain('h-20');
    expect(screen.getByRole('heading', { name: '组织架构' }).className).toContain('text-base');
    expect(screen.getByText('维护组织与用户，并分配角色。').className).toContain('line-clamp-2');
    expect(screen.getByText('维护组织与用户，并分配角色。').className).toContain('text-xs');
  });
});
