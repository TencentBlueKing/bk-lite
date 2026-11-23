// @vitest-environment jsdom

import React, { StrictMode } from 'react';
import { cleanup, render } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { useArchitectureMonitorLink } from '../useMonitorLink';

const getMonitorLink = vi.hoisted(() => vi.fn());

vi.mock('@/app/ops-analysis/api/architecture', () => ({
  useArchitectureApi: () => ({ getMonitorLink }),
}));

const Probe = ({ monitorId }: { monitorId: string }) => {
  useArchitectureMonitorLink(monitorId);
  return null;
};

afterEach(() => {
  cleanup();
  getMonitorLink.mockReset();
});

const hang = () => new Promise(() => undefined);

describe('useArchitectureMonitorLink', () => {
  it('aborts the old monitor link on a real canvas switch and leaves the new request running', async () => {
    getMonitorLink.mockImplementation(hang);
    const view = render(
      <StrictMode>
        <Probe key="canvas-a" monitorId="mon-a" />
      </StrictMode>,
    );
    await vi.waitFor(() => expect(getMonitorLink).toHaveBeenCalled());
    const first = getMonitorLink.mock.calls.at(-1)?.[1] as AbortSignal;
    expect(first.aborted).toBe(false);

    view.rerender(
      <StrictMode>
        <Probe key="canvas-b" monitorId="mon-b" />
      </StrictMode>,
    );
    await vi.waitFor(() => expect(getMonitorLink.mock.calls.length).toBeGreaterThan(1));
    const second = getMonitorLink.mock.calls.at(-1)?.[1] as AbortSignal;
    expect(first.aborted).toBe(true);
    expect(second).not.toBe(first);
    expect(second.aborted).toBe(false);
    expect(getMonitorLink.mock.calls.at(-1)?.[0]).toBe('mon-b');
  });
});
