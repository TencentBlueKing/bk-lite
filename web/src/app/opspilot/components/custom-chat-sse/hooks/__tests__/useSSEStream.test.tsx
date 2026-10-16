import { act, renderHook } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { CustomChatMessage } from '@/app/opspilot/types/global';
import { useSSEStream } from '../useSSEStream';

class ControlledReader {
  private pending: ((result: ReadableStreamReadResult<Uint8Array>) => void) | null = null;
  private abortError: Error | null = null;

  read(): Promise<ReadableStreamReadResult<Uint8Array>> {
    if (this.abortError) {
      return Promise.reject(this.abortError);
    }
    return new Promise((resolve, reject) => {
      this.pending = (result) => {
        this.pending = null;
        if (this.abortError) {
          reject(this.abortError);
          return;
        }
        resolve(result);
      };
    });
  }

  push(message: string) {
    const resolve = this.pending;
    if (!resolve) {
      throw new Error('SSE reader is not waiting');
    }
    resolve({ done: false, value: new TextEncoder().encode(message) });
  }

  finish() {
    const resolve = this.pending;
    if (!resolve) return;
    resolve({ done: true, value: undefined });
  }

  abort() {
    this.abortError = new DOMException('The operation was aborted.', 'AbortError');
    this.pending?.({ done: true, value: undefined });
  }

  async waitUntilWaiting() {
    for (let attempt = 0; attempt < 30; attempt += 1) {
      if (this.pending) return;
      await new Promise((resolve) => setTimeout(resolve, 0));
    }
    throw new Error('SSE reader is not waiting');
  }
}

const sseResponse = (reader: ControlledReader, signal?: AbortSignal) => {
  signal?.addEventListener('abort', () => reader.abort());
  return {
    ok: true,
    headers: { get: () => null },
    body: { getReader: () => reader },
  };
};

describe('useSSEStream close policy', () => {
  const readers: ControlledReader[] = [];

  afterEach(() => {
    vi.unstubAllGlobals();
    readers.length = 0;
  });

  const start = (useAGUIProtocol: boolean) => {
    const messages: CustomChatMessage[] = [{ id: 'bot-1', role: 'bot', content: '' }];
    const updateMessages = (updater: (prev: CustomChatMessage[]) => CustomChatMessage[]) => {
      const next = updater(messages);
      messages.splice(0, messages.length, ...next);
    };
    const setLoading = vi.fn();
    const hook = renderHook(() => useSSEStream({
      token: null,
      useAGUIProtocol,
      updateMessages,
      setLoading,
      t: (key: string) => key,
    }));
    return { hook, messages };
  };

  const installFetch = () => {
    const reader = new ControlledReader();
    readers.push(reader);
    vi.stubGlobal('fetch', vi.fn(async (_url: string, init?: RequestInit) => sseResponse(reader, init?.signal ?? undefined)));
    return reader;
  };

  it('completes a non-AGUI success stream without an error card', async () => {
    const reader = installFetch();
    const { hook, messages } = start(false);
    let done: Promise<void> | undefined;
    await act(async () => {
      done = hook.result.current.handleSSEStream('/chat', {}, messages[0]);
      await reader.waitUntilWaiting();
    });
    await act(async () => {
      reader.push('data: {"choices":[{"delta":{"content":"hello"}}]}\n\n');
      await reader.waitUntilWaiting();
    });
    await act(async () => {
      reader.push('data: {"choices":[{"finish_reason":"stop"}]}\n\n');
      await done;
    });

    expect(messages[0].content).toBe('hello');
    expect(messages[0].content).not.toContain('运行错误');
    expect(messages[0].content).not.toContain('chat.connectionError');
    expect(messages[0].isStreamingTools).toBe(false);
  });

  it('does not append run_error text when the stream is aborted', async () => {
    const reader = installFetch();
    const { hook, messages } = start(false);
    let done: Promise<void> | undefined;
    await act(async () => {
      done = hook.result.current.handleSSEStream('/chat', {}, messages[0]);
      await reader.waitUntilWaiting();
    });
    await act(async () => {
      reader.push('data: {"choices":[{"delta":{"content":"hello"}}]}\n\n');
      await reader.waitUntilWaiting();
    });
    await act(async () => {
      hook.result.current.stopSSEConnection();
      await done;
    });

    expect(messages[0].content).toContain('hello');
    expect(messages[0].content).not.toContain('运行错误');
    expect(messages[0].content).not.toContain('❌');
    expect(messages[0].content).not.toContain('chat.connectionError');
    expect(messages[0].isStreamingTools).toBe(false);
  });

  it('closes a truncated stream and keeps the partial text', async () => {
    const reader = installFetch();
    const { hook, messages } = start(false);
    let done: Promise<void> | undefined;
    await act(async () => {
      done = hook.result.current.handleSSEStream('/chat', {}, messages[0]);
      await reader.waitUntilWaiting();
    });
    await act(async () => {
      reader.push('data: {"choices":[{"delta":{"content":"hello"}}]}\n\n');
      await reader.waitUntilWaiting();
    });
    await act(async () => {
      reader.finish();
      await done;
    });

    expect(messages[0].content).toContain('hello');
    expect(messages[0].content).toContain('chat.connectionError');
    expect(messages[0].isStreamingTools).toBe(false);
  });

  it('completes an AGUI run without treating RUN_FINISHED as a connection error', async () => {
    const reader = installFetch();
    const { hook, messages } = start(true);
    let done: Promise<void> | undefined;
    await act(async () => {
      done = hook.result.current.handleSSEStream('/chat', {}, messages[0]);
      await reader.waitUntilWaiting();
    });
    await act(async () => {
      reader.push('data: {"type":"TEXT_MESSAGE_CONTENT","timestamp":1,"delta":"已完成"}\n\n');
      await reader.waitUntilWaiting();
    });
    await act(async () => {
      reader.push('data: {"type":"RUN_FINISHED","timestamp":2}\n\n');
      await done;
    });

    expect(messages[0].content).toContain('已完成');
    expect(messages[0].content).not.toContain('chat.connectionError');
    expect(messages[0].content).not.toContain('运行错误');
    expect(messages[0].isStreamingTools).toBe(false);
  });
});
