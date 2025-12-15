/**
 * Tauri API 代理客户端
 * 使用 Tauri 命令来处理 HTTP 请求，避免 CORS 问题
 */

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

export interface StreamChunk {
  stream_id: string;
  data: string;
}

export interface StreamEnd {
  stream_id: string;
}

export interface StreamError {
  stream_id: string;
  error: string;
}

/**
 * 安全地调用 Tauri invoke
 * Tauri 2.x 使用 __TAURI_INTERNALS__ 作为主要标识
 */
async function safeInvoke<T>(cmd: string, args?: any): Promise<T> {
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

/**
 * 兼容 fetch API 的 Tauri 代理包装器
 */
export async function tauriApiFetch(
  url: string,
  options: RequestInit = {}
): Promise<Response> {
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

  // 处理请求体
  let body: string | undefined;
  if (options.body) {
    if (typeof options.body === 'string') {
      body = options.body;
    } else {
      body = JSON.stringify(options.body);
    }
  }

  // 动态导入 Tauri API
  const { invoke } = await import('@tauri-apps/api/core');
  const { listen } = await import('@tauri-apps/api/event');

  // 调用 Rust 流式命令，获取 stream_id
  const streamId = await invoke<string>('api_stream_proxy', {
    request: {
      url,
      method,
      headers,
      body,
    },
  });

  // 创建 Promise 队列来缓存接收到的数据块
  const queue: string[] = [];
  let isStreamEnded = false;
  let streamError: Error | null = null;
  let resolveNext: ((value: IteratorResult<string>) => void) | null = null;

  // 监听流数据块事件
  const unlistenChunk = await listen<StreamChunk>('stream-chunk', (event) => {
    if (event.payload.stream_id === streamId) {
      const data = event.payload.data;

      if (resolveNext) {
        // 如果有等待的 Promise，直接解决它
        resolveNext({ value: data, done: false });
        resolveNext = null;
      } else {
        // 否则加入队列
        queue.push(data);
      }
    }
  });

  // 监听流结束事件
  const unlistenEnd = await listen<StreamEnd>('stream-end', (event) => {
    if (event.payload.stream_id === streamId) {
      isStreamEnded = true;

      if (resolveNext) {
        resolveNext({ value: undefined as any, done: true });
        resolveNext = null;
      }
    }
  });

  // 监听流错误事件
  const unlistenError = await listen<StreamError>('stream-error', (event) => {
    console.error('[TauriStream] Stream error:', event.payload.error);
    if (event.payload.stream_id === streamId) {
      streamError = new Error(event.payload.error);
      isStreamEnded = true;

      if (resolveNext) {
        resolveNext({ value: undefined as any, done: true });
        resolveNext = null;
      }
    }
  });

  try {
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

      const result = await new Promise<IteratorResult<string>>((resolve) => {
        resolveNext = resolve;
      });

      // 如果有值，yield 它
      if (!result.done && result.value) {
        yield result.value;
      }

      // 如果 done 为 true，回到循环顶部检查队列和状态
    }

  } finally {
    // 清理事件监听器
    unlistenChunk();
    unlistenEnd();
    unlistenError();
  }
}
