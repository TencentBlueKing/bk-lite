/**
 * Tauri API 代理客户端
 * 使用 Tauri 命令来处理 HTTP 请求，避免 CORS 问题
 */

import { getUserInfoSync } from './secureStorage';
import { getCurrentTeamCookie, resolveDefaultCurrentTeamId } from './teamCookie';

export interface ApiRequest {
  url: string;
  method: string;
  headers?: Record<string, string>;
  body?: string;
}

export interface ApiResponse {
  status: number;
  headers: Record<string, string>;
  body: string;
}

export interface ApiError {
  message: string;
  status?: number;
}

export interface CurrentTeamResolution {
  value: string | null;
  source: 'cookie' | 'stored-login-info' | 'missing';
}

type NativeStreamEvent =
  | { event: 'chunk'; data: string }
  | { event: 'end' }
  | { event: 'error'; error: string; status?: number };

export class TauriStreamError extends Error {
  constructor(message: string, public readonly status?: number) {
    super(message);
    this.name = 'TauriStreamError';
  }
}

/**
 * 安全地调用 Tauri invoke
 * Tauri 2.x 使用 __TAURI_INTERNALS__ 作为主要标识
 */
async function safeInvoke<T>(cmd: string, args?: Record<string, unknown>): Promise<T> {
  // 检查 Tauri 运行时是否可用
  if (typeof window === 'undefined') {
    throw new Error('Tauri is not available: window is undefined');
  }

  // Tauri 2.x 检查 __TAURI_INTERNALS__
  if (!('__TAURI_INTERNALS__' in window)) {
    throw new Error('Tauri is not available: __TAURI_INTERNALS__ not found');
  }

  try {
    // 动态导入 Tauri API
    const { invoke } = await import('@tauri-apps/api/core');

    if (typeof invoke !== 'function') {
      throw new Error('Tauri invoke is not a function');
    }

    return await invoke<T>(cmd, args);
  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : String(error);
    throw new Error(`Tauri invoke failed: ${errorMessage}`);
  }
}

/**
 * 使用 Tauri 命令代理 API 请求
 */
export async function tauriApiProxy(request: ApiRequest): Promise<ApiResponse> {
  try {
    return await safeInvoke<ApiResponse>('api_proxy', { request });
  } catch (error) {
    console.error('[TauriAPI] Request failed:', error);
    throw error;
  }
}

/**
 * 检测当前请求是否通过 Tauri 代理
 */
export function isTauriProxiedResponse(response: Response): boolean {
  return response.headers.get('x-tauri-proxied') === 'true';
}

/**
 * 获取 Tauri 代理信息
 */
export function getTauriProxyInfo(response: Response): {
  proxied: boolean;
  requestId?: string;
  elapsedMs?: number;
} {
  return {
    proxied: response.headers.get('x-tauri-proxied') === 'true',
    requestId: response.headers.get('x-tauri-request-id') || undefined,
    elapsedMs: response.headers.get('x-tauri-elapsed-ms') ?
      parseInt(response.headers.get('x-tauri-elapsed-ms')!) : undefined,
  };
}

export function resolveCurrentTeamForNativeProxy(): CurrentTeamResolution {
  const cookieTeam = getCurrentTeamCookie();
  const storageTeam = cookieTeam ? null : resolveDefaultCurrentTeamId(getUserInfoSync());
  const currentTeam = cookieTeam ?? storageTeam;

  return {
    value: currentTeam,
    source: currentTeam ? (cookieTeam ? 'cookie' : 'stored-login-info') : 'missing',
  };
}

function appendCurrentTeamCookie(headers: Record<string, string>) {
  const currentTeam = resolveCurrentTeamForNativeProxy();
  if (!currentTeam.value) {
    return;
  }

  const cookieHeaderKey = Object.keys(headers).find((key) => key.toLowerCase() === 'cookie');
  const currentTeamCookie = `current_team=${encodeURIComponent(currentTeam.value)}`;

  if (cookieHeaderKey) {
    const existingCookie = headers[cookieHeaderKey];
    if (!existingCookie.includes('current_team=')) {
      headers[cookieHeaderKey] = `${existingCookie}; ${currentTeamCookie}`;
    }
    return;
  }

  headers.Cookie = currentTeamCookie;
}

/**
 * 兼容 fetch API 的 Tauri 代理包装器
 */
export async function tauriApiFetch(
  url: string,
  options: RequestInit = {}
): Promise<Response> {
  if (options.signal?.aborted) {
    throw new DOMException('The operation was aborted', 'AbortError');
  }

  const method = options.method || 'GET';
  const headers: Record<string, string> = {};

  // 转换 Headers 对象到普通对象
  if (options.headers) {
    if (options.headers instanceof Headers) {
      options.headers.forEach((value, key) => {
        headers[key] = value;
      });
    } else if (typeof options.headers === 'object') {
      Object.assign(headers, options.headers);
    }
  }

  appendCurrentTeamCookie(headers);

  // 处理请求体
  let body: string | undefined;
  if (options.body) {
    if (typeof options.body === 'string') {
      body = options.body;
    } else {
      body = JSON.stringify(options.body);
    }
  }

  const response = await tauriApiProxy({
    url,
    method,
    headers,
    body,
  });

  // 原生非流式请求暂不支持中途取消，但取消后的响应不得再进入业务状态。
  if (options.signal?.aborted) {
    throw new DOMException('The operation was aborted', 'AbortError');
  }

  // 创建兼容的 Response 对象
  return new Response(response.body, {
    status: response.status,
    statusText: response.status >= 200 && response.status < 300 ? 'OK' : 'Error',
    headers: new Headers(response.headers),
  });
}

/**
 * Tauri 流式请求（真正的流式体验）
 * 返回一个异步生成器，通过 Tauri 事件系统实时接收数据
 */
export async function* tauriApiStream(
  url: string,
  options: RequestInit = {}
): AsyncGenerator<string, void, unknown> {
  const method = options.method || 'POST';
  const headers: Record<string, string> = {};

  // 转换 Headers 对象到普通对象
  if (options.headers) {
    if (options.headers instanceof Headers) {
      options.headers.forEach((value, key) => {
        headers[key] = value;
      });
    } else if (typeof options.headers === 'object') {
      Object.assign(headers, options.headers);
    }
  }

  appendCurrentTeamCookie(headers);

  // 处理请求体
  let body: string | undefined;
  if (options.body) {
    if (typeof options.body === 'string') {
      body = options.body;
    } else {
      body = JSON.stringify(options.body);
    }
  }

  const { Channel, invoke } = await import('@tauri-apps/api/core');
  const queue: string[] = [];
  let isStreamEnded = false;
  let streamError: TauriStreamError | null = null;
  let resolveNext: (() => void) | null = null;
  let streamId: string | null = null;
  const signal = options.signal;
  const wakeConsumer = () => {
    resolveNext?.();
    resolveNext = null;
  };
  const handleAbort = () => {
    queue.length = 0;
    streamError = null;
    isStreamEnded = true;
    wakeConsumer();
  };

  if (signal?.aborted) {
    return;
  }
  signal?.addEventListener('abort', handleAbort, { once: true });

  const onEvent = new Channel<NativeStreamEvent>();
  onEvent.onmessage = (event) => {
    if (signal?.aborted || isStreamEnded) {
      return;
    }
    switch (event.event) {
      case 'chunk':
        queue.push(event.data);
        break;
      case 'end':
        isStreamEnded = true;
        break;
      case 'error':
        streamError = new TauriStreamError(event.error, event.status);
        isStreamEnded = true;
        break;
      default: {
        const exhaustiveCheck: never = event;
        throw new Error(`Unsupported native stream event: ${String(exhaustiveCheck)}`);
      }
    }
    wakeConsumer();
  };

  try {
    streamId = await invoke<string>('api_stream_proxy', {
      request: {
        url,
        method,
        headers,
        body,
      },
      onEvent,
    });

    // 异步生成器主循环
    while (true) {
      // 优先处理队列中的数据
      while (queue.length > 0) {
        const data = queue.shift()!;
        yield data;
      }

      // 队列已空，检查流状态
      if (streamError) {
        throw streamError;
      }

      if (isStreamEnded) {
        break;
      }

      await new Promise<void>((resolve) => {
        resolveNext = resolve;
      });
    }

  } finally {
    signal?.removeEventListener('abort', handleAbort);
    if (streamId) {
      // 通知 Rust 侧取消流（若流已自然结束则 Rust 侧会静默忽略）
      try {
        await invoke('cancel_stream', { streamId });
      } catch {
        // 忽略取消命令本身的错误（如 Rust 侧已结束）
      }
    }
  }
}
