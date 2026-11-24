// @vitest-environment jsdom

import { cleanup, render } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { useArchitectureNodeStatus } from '../useNodeStatus';

const queryNodeStatus = vi.hoisted(() => vi.fn());

vi.mock('@/app/ops-analysis/api/architecture', () => ({
  useArchitectureApi: () => ({ queryNodeStatus }),
}));

const Probe = () => {
  useArchitectureNodeStatus({
    enabled: true,
    uuids: ['inst-1'],
    intervalMs: 0,
  });
  return null;
};

afterEach(() => {
  cleanup();
  queryNodeStatus.mockReset();
});

describe('useArchitectureNodeStatus', () => {
  it('aborts the in-flight status post when the canvas unmounts', async () => {
    let signal: AbortSignal | undefined;
    queryNodeStatus.mockImplementation((_uuids: string[], next?: AbortSignal) => new Promise((_resolve, reject) => {
      signal = next;
      next?.addEventListener('abort', () => {
        reject(Object.assign(new Error('canceled'), { name: 'CanceledError', code: 'ERR_CANCELED' }));
      }, { once: true });
    }));
    const view = render(<Probe />);
    await vi.waitFor(() => expect(signal).toBeInstanceOf(AbortSignal));
    view.unmount();
    expect(signal?.aborted).toBe(true);
  });
});
