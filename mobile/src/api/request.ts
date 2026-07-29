import { tauriFetch, isTauriApp } from '../utils/tauriFetch';
import { TauriStreamError, tauriApiStream } from '../utils/tauriApiProxy';
import { getTokenSync, clearAuthData } from '../utils/secureStorage';
import { withBasePath } from '../utils/basePath';
import { clearCurrentTeamCookie } from '../utils/teamCookie';

const API_PROXY_PREFIX = '/api/proxy';
const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, '') || '';
const TARGET_SERVER = `${API_BASE_URL}${API_PROXY_PREFIX}`;
let runtimeAuthToken: string | null | undefined = null;
let unauthorizedHandler: (() => void | Promise<void>) | null = null;
let unauthorizedHandling: Promise<void> | null = null;

export class UnauthorizedRequestError extends Error {
  constructor() {
    super('Authentication required');
    this.name = 'UnauthorizedRequestError';
  }
}

function resolveApiAuthToken(
  runtimeToken: string | null | undefined,
  storedToken: string | null,
): string | null {
  return runtimeToken === undefined ? storedToken : runtimeToken;
}

export function setRuntimeAuthToken(token: string | null | undefined) {
  runtimeAuthToken = token;
}

export function setUnauthorizedHandler(handler: (() => void | Promise<void>) | null) {
  unauthorizedHandler = handler;
}

function normalizeApiEndpoint(
  endpoint: string,
  options: { trailingSlash?: boolean } = {},
): string {
  const trailingSlash = options.trailingSlash ?? true;
  const value = endpoint.startsWith('/') ? endpoint : `/${endpoint}`;
  const suffixIndex = value.search(/[?#]/);
  const pathname = suffixIndex === -1 ? value : value.slice(0, suffixIndex);
  const suffix = suffixIndex === -1 ? '' : value.slice(suffixIndex);
  const normalizedPath = trailingSlash
    ? (pathname.endsWith('/') ? pathname : `${pathname}/`)
    : (pathname === '/' ? pathname : pathname.replace(/\/+$/, ''));

  return `${normalizedPath}${suffix}`;
}

function buildTargetUrl(endpoint: string): string {
  return `${TARGET_SERVER}${normalizeApiEndpoint(endpoint, {
    trailingSlash: !isTauriApp(),
  })}`;
}

/**
 * 处理 401 未授权错误
 * 清空认证信息并跳转到登录页
 */
async function handle401Error(requestToken: string | null) {
  const currentToken = resolveApiAuthToken(runtimeAuthToken, getTokenSync());
  if (requestToken !== currentToken) {
    return;
  }

  if (unauthorizedHandling) {
    await unauthorizedHandling;
    return;
  }

  unauthorizedHandling = (async () => {
    if (unauthorizedHandler) {
      await unauthorizedHandler();
      return;
    }

    await clearAuthData();
    clearCurrentTeamCookie();

    if (typeof window !== 'undefined') {
      window.location.href = withBasePath('/login');
    }
  })();

  try {
    await unauthorizedHandling;
  } finally {
    unauthorizedHandling = null;
  }
}

export async function apiRequest<T = any>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const targetUrl = buildTargetUrl(endpoint);
  // 从安全存储的内存缓存获取 token（同步方法）
  const token = resolveApiAuthToken(runtimeAuthToken, getTokenSync());

  const config: RequestInit = {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(token && { Authorization: `Bearer ${token}` }),
      ...options.headers,
    },
    mode: 'cors',
    credentials: 'include',
  };

  try {
    // 统一使用 tauriFetch，自动选择最佳方式（Tauri Rust 代理 > 标准 fetch）
    const response = await tauriFetch(targetUrl, config);

    // 检查 401 未授权错误
    if (response.status === 401) {
      await handle401Error(token);
      throw new UnauthorizedRequestError();
    }

    // 检查其他响应状态
    if (!response.ok) {
      let errorText = '';
      try {
        errorText = await response.text();
      } catch {
        errorText = 'Unable to parse error response';
      }
      throw new Error(`API Error: ${response.status} - ${errorText}`);
    }

    // 尝试解析 JSON
    const contentType = response.headers.get('content-type');
    if (contentType && contentType.includes('application/json')) {
      return await response.json();
    }

    // 返回文本响应
    return await response.text() as any;

  } catch (error: unknown) {
    if (
      error instanceof UnauthorizedRequestError
      || (error instanceof Error && error.name === 'AbortError')
    ) {
      throw error;
    }

    console.error('[API] Request failed:', targetUrl, error);
    throw error;
  }
}

/**
 * GET 请求
 */
export async function apiGet<T = any>(
  endpoint: string,
  params?: Record<string, any>,
  options?: RequestInit
): Promise<T> {
  // 构建查询字符串
  let url = endpoint;
  if (params) {
    const queryString = Object.entries(params)
      .filter(([_, value]) => value !== undefined && value !== null && value !== '')
      .map(([key, value]) => `${encodeURIComponent(key)}=${encodeURIComponent(value)}`)
      .join('&');
    if (queryString) {
      url = `${endpoint}?${queryString}`;
    }
  }

  return apiRequest<T>(url, {
    ...options,
    method: 'GET',
  });
}

/**
 * POST 请求
 */
export async function apiPost<T = any>(
  endpoint: string,
  data?: any,
  options?: RequestInit
): Promise<T> {
  return apiRequest<T>(endpoint, {
    ...options,
    method: 'POST',
    body: data ? JSON.stringify(data) : undefined,
  });
}

/**
 * PUT 请求
 */
export async function apiPut<T = any>(
  endpoint: string,
  data?: any,
  options?: RequestInit
): Promise<T> {
  return apiRequest<T>(endpoint, {
    ...options,
    method: 'PUT',
    body: data ? JSON.stringify(data) : undefined,
  });
}

/**
 * DELETE 请求
 */
export async function apiDelete<T = any>(
  endpoint: string,
  options?: RequestInit
): Promise<T> {
  return apiRequest<T>(endpoint, {
    ...options,
    method: 'DELETE',
  });
}

/**
 * PATCH 请求
 */
export async function apiPatch<T = any>(
  endpoint: string,
  data?: any,
  options?: RequestInit
): Promise<T> {
  return apiRequest<T>(endpoint, {
    ...options,
    method: 'PATCH',
    body: data ? JSON.stringify(data) : undefined,
  });
}

class SseDataDecoder {
  private buffer = '';
  private waitingForDataValue = false;

  push(chunk: string, flush = false): string[] {
    this.buffer += chunk;
    const lines = this.buffer.split('\n');
    this.buffer = flush ? '' : (lines.pop() ?? '');
    const payloads: string[] = [];

    for (const rawLine of lines) {
      const line = rawLine.trim();
      if (!line || line.startsWith(':')) {
        continue;
      }

      if (line.startsWith('data:')) {
        const payload = line.slice(5).trim();
        if (payload) {
          this.waitingForDataValue = false;
          payloads.push(payload);
        } else {
          // 兼容服务端将 `data:` 与 JSON 放在相邻两行的历史格式。
          this.waitingForDataValue = true;
        }
        continue;
      }

      if (
        this.waitingForDataValue
        && (line.startsWith('{') || line.startsWith('['))
      ) {
        this.waitingForDataValue = false;
        payloads.push(line);
      }
    }

    return payloads;
  }

  finish(): string[] {
    return this.push('', true);
  }
}

function parseSsePayload<T>(payload: string): T | null {
  if (payload === '[DONE]') {
    return null;
  }

  let parsed: unknown;
  try {
    parsed = JSON.parse(payload);
  } catch {
    throw new Error('Invalid SSE JSON payload');
  }

  if (typeof parsed !== 'object' || parsed === null) {
    throw new Error('Invalid SSE event payload');
  }

  const event = parsed as Record<string, unknown>;
  if (
    event.result === false
    || (event.error && !event.type)
    || event.type === 'ERROR'
    || event.type === 'RUN_ERROR'
  ) {
    const message = event.error ?? event.message ?? 'Server returned an error';
    throw new Error(String(message));
  }

  return parsed as T;
}

/**
 * SSE 流式请求
 * 返回一个异步生成器，用于处理服务器发送事件(Server-Sent Events)
 * Tauri 环境下使用 Rust 原生流式处理，浏览器环境使用标准 fetch
 */
export async function* apiStream<T = any>(
  endpoint: string,
  data?: any,
  options?: RequestInit
): AsyncGenerator<T, void, unknown> {
  const targetUrl = buildTargetUrl(endpoint);
  const token = resolveApiAuthToken(runtimeAuthToken, getTokenSync());

  const config: RequestInit = {
    ...options,
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Accept': 'text/event-stream',
      ...(token && { Authorization: `Bearer ${token}` }),
      ...options?.headers,
    },
    body: data ? JSON.stringify(data) : undefined,
    mode: 'cors',
    credentials: 'include',
  };

  // Tauri 环境下使用 Rust 原生流式处理
  if (isTauriApp()) {
    const decoder = new SseDataDecoder();
    let hasReceivedValidEvent = false;

    try {
      for await (const chunk of tauriApiStream(targetUrl, config)) {
        for (const payload of decoder.push(chunk)) {
          const event = parseSsePayload<T>(payload);
          if (event !== null) {
            hasReceivedValidEvent = true;
            yield event;
          }
        }
      }

      for (const payload of decoder.finish()) {
        const event = parseSsePayload<T>(payload);
        if (event !== null) {
          hasReceivedValidEvent = true;
          yield event;
        }
      }

      if (config.signal?.aborted) {
        return;
      }

      if (!hasReceivedValidEvent) {
        throw new Error('未收到有效的 AI 响应');
      }

      return;
    } catch (error) {
      if (config.signal?.aborted || (error instanceof Error && error.name === 'AbortError')) {
        return;
      }
      if (error instanceof TauriStreamError && error.status === 401) {
        await handle401Error(token);
        throw new UnauthorizedRequestError();
      }
      console.error('[API Stream] Tauri streaming error:', error);
      throw error;
    }
  }

  const response = await tauriFetch(targetUrl, config);

  if (response.status === 401) {
    await handle401Error(token);
    throw new UnauthorizedRequestError();
  }

  if (!response.ok) {
    throw new Error(`API Stream Error: ${response.status}`);
  }

  // 检查响应类型，如果是 JSON 错误响应则直接处理
  const contentType = response.headers.get('content-type') || '';

  // 如果返回的是 JSON 而不是 SSE 流，可能是错误响应
  if (contentType.includes('application/json')) {
    const jsonResponse = await response.json();
    // 检查是否是错误响应
    if (jsonResponse.result === false || jsonResponse.error) {
      throw new Error(jsonResponse.error || '服务器返回错误');
    }
    // 如果是其他 JSON 响应，也抛出错误（因为期望的是 SSE 流）
    throw new Error('服务器返回了非预期的响应格式');
  }

  const reader = response.body?.getReader();
  if (!reader) {
    throw new Error('Response body is not readable');
  }

  const textDecoder = new TextDecoder();
  const sseDecoder = new SseDataDecoder();
  let hasReceivedValidEvent = false;

  try {
    while (true) {
      const { done, value } = await reader.read();

      if (done) break;

      const text = textDecoder.decode(value, { stream: true });
      for (const payload of sseDecoder.push(text)) {
        const event = parseSsePayload<T>(payload);
        if (event !== null) {
          hasReceivedValidEvent = true;
          yield event;
        }
      }
    }

    const finalText = textDecoder.decode();
    for (const payload of [
      ...sseDecoder.push(finalText),
      ...sseDecoder.finish(),
    ]) {
      const event = parseSsePayload<T>(payload);
      if (event !== null) {
        hasReceivedValidEvent = true;
        yield event;
      }
    }

    // 如果整个流程没有收到任何有效事件，抛出错误
    if (!hasReceivedValidEvent) {
      throw new Error('未收到有效的 AI 响应');
    }
  } finally {
    reader.releaseLock();
  }
}
