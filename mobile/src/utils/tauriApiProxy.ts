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
