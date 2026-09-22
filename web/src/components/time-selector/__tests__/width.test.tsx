// @vitest-environment jsdom

import { cleanup, render } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest';

import TimeSelector from '@/components/time-selector';

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

beforeEach(() => {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: vi.fn().mockImplementation((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  });
});

afterEach(cleanup);

describe('TimeSelector width', () => {
  test('默认仍是 350px，不撑破页面工具栏', () => {
    const { container } = render(<TimeSelector onlyTimeSelect />);
    const select = container.querySelector('.ant-select');
    expect(select?.className).toContain('w-[350px]');
    expect(select?.className).not.toContain('w-full');
  });

  test('className=w-full 时内部选择器跟父级宽度走', () => {
    const { container } = render(
      <div style={{ width: 200 }}>
        <TimeSelector onlyTimeSelect className="w-full" />
      </div>,
    );
    const select = container.querySelector('.ant-select');
    expect(select?.className).toContain('w-full');
    expect(select?.className).not.toContain('w-[350px]');
  });
});
