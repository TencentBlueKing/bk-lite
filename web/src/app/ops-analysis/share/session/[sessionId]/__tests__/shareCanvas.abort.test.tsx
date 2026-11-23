// @vitest-environment jsdom

import React, { StrictMode } from 'react';
import { cleanup, render } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import ShareDashboardPage from '@/app/ops-analysis/share/session/[sessionId]/shareDashboardPage';

const getSharedCanvas = vi.hoisted(() => vi.fn());

vi.mock('next/navigation', () => ({
  useParams: () => ({ sessionId: 'session-1' }),
  useRouter: () => ({ push: vi.fn() }),
}));

vi.mock('@/app/ops-analysis/(pages)/view/dashBoard', () => ({ default: () => null }));
vi.mock('@/app/ops-analysis/(pages)/view/topology', () => ({ default: () => null }));
vi.mock('@/app/ops-analysis/(pages)/view/architecture', () => ({ default: () => null }));
vi.mock('@/app/ops-analysis/(pages)/view/screen', () => ({ default: () => null }));
vi.mock('@/app/ops-analysis/(pages)/view/report', () => ({ default: () => null }));
vi.mock('@/app/ops-analysis/(pages)/view/networkTopology', () => ({ default: () => null }));

vi.mock('@/app/ops-analysis/api/dashboardShare', () => ({
  useCanvasShareApi: () => ({
    getSharedCanvas,
    querySharedDataSource: vi.fn(),
    resolveSharedOptionSource: vi.fn(),
    getSharedDataSources: vi.fn(),
    getSharedNetworkTopologyMetricValues: vi.fn(),
    getSharedNetworkTopologyLinkRuntime: vi.fn(),
  }),
}));

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock('@/app/ops-analysis/context/common', () => ({
  OpsAnalysisProvider: ({ children }: { children: React.ReactNode }) => children,
}));

afterEach(() => {
  cleanup();
  getSharedCanvas.mockReset();
});

describe('shared canvas bootstrap', () => {
  it('aborts the session canvas read on unmount without treating it as a load failure', async () => {
    getSharedCanvas.mockImplementation(() => new Promise(() => undefined));
    const view = render(
      <StrictMode>
        <ShareDashboardPage />
      </StrictMode>,
    );
    await vi.waitFor(() => expect(getSharedCanvas).toHaveBeenCalled());
    const live = getSharedCanvas.mock.calls
      .map((call) => call[1] as AbortSignal)
      .filter((signal) => signal && !signal.aborted);
    expect(getSharedCanvas.mock.calls.at(-1)?.[0]).toBe('session-1');
    expect(live.length).toBeGreaterThan(0);
    view.unmount();
    expect(live.every((signal) => signal.aborted)).toBe(true);
    expect(document.body.textContent).not.toContain('网络异常');
  });
});
