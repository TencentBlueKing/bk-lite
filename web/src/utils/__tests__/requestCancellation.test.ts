import { describe, expect, it, vi } from 'vitest';

import { fetchWidgetData } from '@/app/ops-analysis/utils/widgetDataTransform';
import {
  createTransportCancelError,
  isTransportCanceled,
  waitUntilDelayOrAbort,
} from '@/utils/requestCancellation';
import { sourceDataRequestConfig } from '@/app/ops-analysis/api/dataSource';

describe('request cancellation', () => {
  it('recognizes transport cancellation and leaves timeout and network errors alone', () => {
    expect(isTransportCanceled(createTransportCancelError())).toBe(true);
    const abortError = new Error('The operation was aborted.');
    abortError.name = 'AbortError';
    expect(isTransportCanceled(abortError)).toBe(true);
    expect(isTransportCanceled(Object.assign(new Error('timeout'), { code: 'ECONNABORTED' }))).toBe(false);
    expect(isTransportCanceled(Object.assign(new Error('network'), { code: 'ERR_NETWORK' }))).toBe(false);
  });

  it('rejects a backoff wait when the signal aborts and does not resolve it', async () => {
    vi.useFakeTimers();
    const controller = new AbortController();
    const waiting = waitUntilDelayOrAbort(5_000, controller.signal);
    const settled = vi.fn();
    void waiting.then(settled, settled);
    controller.abort();
    await expect(waiting).rejects.toMatchObject({ code: 'ERR_CANCELED' });
    expect(settled).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(5_000);
    expect(settled).toHaveBeenCalledTimes(1);
    vi.useRealTimers();
  });

  it('puts suppress and signal on the shared source-data request config', () => {
    const controller = new AbortController();
    expect(sourceDataRequestConfig({
      suppressErrorNotification: true,
      signal: controller.signal,
    })).toEqual({
      suppressErrorNotification: true,
      signal: controller.signal,
    });
    expect(sourceDataRequestConfig()).toBeUndefined();
  });

  it('does not log a canceled widget fetch and still logs a real failure', async () => {
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {});
    await expect(fetchWidgetData({
      config: { dataSource: 4 },
      getSourceDataByApiId: async () => {
        throw createTransportCancelError();
      },
      throwError: true,
    })).rejects.toMatchObject({ code: 'ERR_CANCELED' });
    expect(consoleError).not.toHaveBeenCalled();

    await expect(fetchWidgetData({
      config: { dataSource: 4 },
      getSourceDataByApiId: async () => {
        throw new Error('获取数据失败');
      },
      throwError: true,
    })).rejects.toThrow('获取数据失败');
    expect(consoleError).toHaveBeenCalled();
    consoleError.mockRestore();
  });
});
