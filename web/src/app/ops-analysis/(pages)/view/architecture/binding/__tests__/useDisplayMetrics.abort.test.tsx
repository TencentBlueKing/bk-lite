// @vitest-environment jsdom

import React, { StrictMode } from 'react';
import { cleanup, render } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { useArchitectureDisplayMetrics } from '../useDisplayMetrics';

const queryDisplayMetrics = vi.hoisted(() => vi.fn());

vi.mock('@/app/ops-analysis/api/architecture', () => ({
  useArchitectureApi: () => ({ queryDisplayMetrics }),
}));

const Probe = ({ uuid }: { uuid: string }) => {
  useArchitectureDisplayMetrics({
    enabled: true,
    uuids: [uuid],
    intervalMs: 0,
    refreshOnVisible: false,
  });
  return null;
};

afterEach(() => {
  cleanup();
  queryDisplayMetrics.mockReset();
});

describe('useArchitectureDisplayMetrics', () => {
  it('aborts the previous metric batch when the canvas unmounts and keeps the replacement', async () => {
    queryDisplayMetrics.mockImplementation(() => new Promise(() => undefined));
    const view = render(
      <StrictMode>
        <Probe key="a" uuid="inst-a" />
      </StrictMode>,
    );
    await vi.waitFor(() => expect(queryDisplayMetrics).toHaveBeenCalled());
    const first = queryDisplayMetrics.mock.calls.at(-1)?.[1] as AbortSignal;

    view.rerender(
      <StrictMode>
        <Probe key="b" uuid="inst-b" />
      </StrictMode>,
    );
    await vi.waitFor(() => {
      const latest = queryDisplayMetrics.mock.calls.at(-1)?.[1] as AbortSignal;
      expect(latest).not.toBe(first);
      expect(latest.aborted).toBe(false);
    });
    const second = queryDisplayMetrics.mock.calls.at(-1)?.[1] as AbortSignal;
    expect(first.aborted).toBe(true);
    expect(queryDisplayMetrics.mock.calls.at(-1)?.[0]).toEqual(['inst-b']);
    view.unmount();
    expect(second.aborted).toBe(true);
  });
});
