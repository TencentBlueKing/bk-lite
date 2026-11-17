// @vitest-environment jsdom

import React from 'react';
import { cleanup, render } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

import WidgetState from '../index';

const mockBox = { width: 0, height: 0 };
const prompt = '数据加载失败';

describe('WidgetState error fit', () => {
  afterEach(() => {
    cleanup();
    mockBox.width = 0;
    mockBox.height = 0;
    vi.restoreAllMocks();
  });

  const renderAt = (width: number, height: number) => {
    mockBox.width = width;
    mockBox.height = height;
    vi.spyOn(HTMLElement.prototype, 'offsetWidth', 'get').mockImplementation(() => mockBox.width);
    vi.spyOn(HTMLElement.prototype, 'offsetHeight', 'get').mockImplementation(() => mockBox.height);
    return render(<WidgetState kind="error" description={prompt} />);
  };

  it('drops the warning icon and uses a smaller font in a small component', () => {
    const small = renderAt(80, 64);
    const smallFont = Number.parseFloat(small.getByText(prompt).style.fontSize);
    const smallHasIcon = Boolean(small.container.querySelector('.anticon'));
    cleanup();

    const large = renderAt(360, 200);
    const largeFont = Number.parseFloat(large.getByText(prompt).style.fontSize);

    expect(smallHasIcon).toBe(false);
    expect(large.container.querySelector('.anticon')).toBeTruthy();
    expect(smallFont).toBeLessThan(largeFont);
  });
});
