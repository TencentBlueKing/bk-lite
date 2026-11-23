import { describe, expect, it, vi } from 'vitest';
import { svgToBase64 } from '@/app/ops-analysis/utils/common';

describe('svgToBase64', () => {
  it('aborts the icon fetch instead of turning it into a fallback icon', async () => {
    const controller = new AbortController();
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(
      (_input: RequestInfo | URL, init?: RequestInit) => new Promise<Response>((_resolve, reject) => {
        const signal = init?.signal;
        if (!signal) return;
        if (signal.aborted) {
          reject(Object.assign(new Error('aborted'), { name: 'AbortError' }));
          return;
        }
        signal.addEventListener('abort', () => {
          reject(Object.assign(new Error('aborted'), { name: 'AbortError' }));
        }, { once: true });
      }),
    );
    const pending = svgToBase64('/assets/icons-realistic/cc-host_主机.svg', controller.signal);
    controller.abort();
    await expect(pending).rejects.toMatchObject({ name: 'AbortError' });
    expect(String(fetchMock.mock.calls[0]?.[0])).toBe('/assets/icons-realistic/cc-host_主机.svg');
    fetchMock.mockRestore();
  });
});
