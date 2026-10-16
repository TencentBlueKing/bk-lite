import React from 'react';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';

import Spin from '@/components/spin';

afterEach(cleanup);

describe('Spin', () => {
  it('renders a neutral local loader by default', () => {
    render(<Spin label="加载列表" />);

    const loader = screen.getByRole('status', { name: '加载列表' });
    expect(loader.className).toContain('inline-flex');
    expect(loader.className).not.toContain('fixed');
    expect(loader.querySelector('.loading-arc')).toBeNull();
    expect(loader.firstElementChild?.className).toContain('border-[var(--color-fill-3)]');
  });

  it('only covers the viewport when fullscreen is explicit', () => {
    render(<Spin fullscreen label="启动应用" />);

    const loader = screen.getByRole('status', { name: '启动应用' });
    expect(loader.className).toContain('fixed');
    expect(loader.className).toContain('inset-0');
    expect(loader.className).toContain('bg-[var(--color-bg)]');
  });
});
