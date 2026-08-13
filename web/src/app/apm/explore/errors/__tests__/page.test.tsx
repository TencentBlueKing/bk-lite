import React from 'react';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import ApmErrorsPage from '../page';

const api = {
  getServices: vi.fn(),
  getTraces: vi.fn(),
  isLoading: false,
};

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));
vi.mock('@/app/apm/api', () => ({ default: () => api }));
vi.mock('@/app/apm/components/apm-route-shell', () => ({
  default: ({ children, showDependencyNote }: { children: React.ReactNode; showDependencyNote?: boolean }) => (
    <main data-show-dependency-note={String(showDependencyNote)}>{children}</main>
  ),
  ApmSurface: ({ children }: { children: React.ReactNode }) => <section>{children}</section>,
}));

beforeEach(() => {
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }));
  api.getServices.mockResolvedValue([]);
  api.getTraces.mockResolvedValue({ items: [] });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('APM 错误页信息层级', () => {
  it('只保留任务所需说明，不重复展示能力规划与遥测依赖文案', async () => {
    const { container } = render(<ApmErrorsPage />);

    await screen.findByText('选择服务与环境后查看错误调用链。');
    expect(screen.queryByText(/当前版本按错误调用链展示/)).toBeNull();
    expect(screen.queryByText(/以下卡片按入口操作做了客户端归并/)).toBeNull();
    expect(container.querySelector('main')?.getAttribute('data-show-dependency-note')).toBe('false');
  });
});
