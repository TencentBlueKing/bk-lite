import React from 'react';
import { act, cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import LogTerminal from '../index';

vi.mock('@/context/auth', () => ({
  useAuth: () => ({ token: 'test-token' }),
}));

vi.mock('@/utils/request', () => ({
  default: () => ({ isLoading: false }),
}));

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

class ControlledReader {
  private pendingRead:
    | ((result: ReadableStreamReadResult<Uint8Array>) => void)
    | null = null;

  read(): Promise<ReadableStreamReadResult<Uint8Array>> {
    return new Promise((resolve) => {
      this.pendingRead = resolve;
    });
  }

  push(message: string) {
    const resolve = this.pendingRead;
    if (!resolve) throw new Error('日志流尚未等待下一段数据');
    this.pendingRead = null;
    resolve({ done: false, value: new TextEncoder().encode(message) });
  }

  finish() {
    const resolve = this.pendingRead;
    if (!resolve) return;
    this.pendingRead = null;
    resolve({ done: true, value: undefined });
  }

  releaseLock() {}
}

describe('LogTerminal', () => {
  let readers: ControlledReader[];
  let signals: AbortSignal[];

  beforeEach(() => {
    HTMLElement.prototype.scrollTo = vi.fn();
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
    readers = [];
    signals = [];
    vi.stubGlobal(
      'fetch',
      vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
        const reader = new ControlledReader();
        const signal = init?.signal;
        readers.push(reader);
        if (signal) {
          signals.push(signal);
          signal.addEventListener('abort', () => reader.finish(), {
            once: true,
          });
        }
        return {
          ok: true,
          body: { getReader: () => reader },
        };
      })
    );
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it('暂停时关闭实时流，继续后建立新的实时流', async () => {
    const user = userEvent.setup();
    render(<LogTerminal query={{ query: '*', log_groups: ['app'] }} />);

    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(1));
    await act(async () => {
      readers[0].push('data: {"message":"暂停前"}\n\n');
    });
    expect(await screen.findByText('暂停前')).not.toBeNull();

    const pauseButton = screen.getByRole('button', {
      name: 'log.search.pauseLogs',
    });
    await user.click(pauseButton);
    expect(signals[0].aborted).toBe(true);
    expect(screen.getByRole('button', { name: 'log.search.resumeLogs' })).not.toBeNull();

    await user.click(
      screen.getByRole('button', { name: 'log.search.resumeLogs' })
    );
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(2));
    expect(signals[1].aborted).toBe(false);
    expect(screen.getByText('暂停前')).not.toBeNull();

    await act(async () => {
      readers[1].push('data: {"message":"继续后"}\n\n');
    });
    expect(await screen.findByText('继续后')).not.toBeNull();
  });
});
