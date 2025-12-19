import { tauriFetch, isTauriApp } from '../utils/tauriFetch';
import { tauriApiStream } from '../utils/tauriApiProxy';
import { getTokenSync, clearAuthData } from '../utils/secureStorage';

const TARGET_SERVER = (process.env.NEXT_PUBLIC_API_URL || 'https://bklite.canway.net') + '/api/v1';

/**
 * 处理 401 未授权错误
 * 清空认证信息并跳转到登录页
 */
async function handle401Error() {
  console.warn('检测到 401 未授权，清空认证信息并跳转到登录页');

  // 清空存储的认证信息
  await clearAuthData();

  // 跳转到登录页
  if (typeof window !== 'undefined') {
    window.location.href = '/login';
  }
}

export async function apiRequest<T = any>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const targetPath = endpoint.replace('/api/proxy', '');

  const targetUrl = `${TARGET_SERVER}${targetPath}`;
  // 从安全存储的内存缓存获取 token（同步方法）
  const token = getTokenSync();

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
      await handle401Error();
      throw new Error('未授权，请重新登录');
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

  } catch (error: any) {
    if (error && (error.name === 'AbortError')) {
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
  const targetPath = endpoint.replace('/api/proxy', '');
  const targetUrl = `${TARGET_SERVER}${targetPath}`;
  const token = getTokenSync();

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
    let buffer = '';
    let hasReceivedValidEvent = false;

    try {

      for await (const chunk of tauriApiStream(targetUrl, config)) {
        buffer += chunk;

        // 按行分割处理 SSE 数据
        const lines = buffer.split('\n');
        buffer = lines.pop() || ''; // 保留最后一个不完整的行

        for (let i = 0; i < lines.length; i++) {
          const line = lines[i];
          const trimmedLine = line.trim();

          // 跳过空行和注释
          if (!trimmedLine || trimmedLine.startsWith(':')) {
            continue;
          }

          // 处理 SSE 数据行
          let jsonStr = '';

          if (trimmedLine === 'data:') {
            // data: 单独一行，下一行是 JSON
            if (i + 1 < lines.length) {
              const nextLine = lines[i + 1].trim();
              if (nextLine && !nextLine.startsWith(':')) {
                jsonStr = nextLine;
                i++; // 跳过下一行
              }
            }
          } else if (trimmedLine.startsWith('data:')) {
            // data: 和 JSON 在同一行
            jsonStr = trimmedLine.slice(5).trim();
          } else {
            // 不是标准 SSE 格式，跳过
            continue;
          }

          // 跳过 [DONE] 标记
          if (jsonStr === '[DONE]') {
            continue;
          }

          if (jsonStr) {
            try {
              const parsed = JSON.parse(jsonStr);

              // 检查是否是错误响应格式
              if (parsed.result === false || (parsed.error && !parsed.type) || parsed.type === 'ERROR' || parsed.type === 'RUN_ERROR') {
                throw new Error(parsed.error || parsed.message || 'Server returned an error');
              }

              // 正常的事件
              hasReceivedValidEvent = true;
              yield parsed as T;
            } catch (e) {
              if (e instanceof Error && e.message) {
                throw e;
              }
              console.warn('[API Stream] Failed to parse SSE event:', jsonStr.substring(0, 100), e);
            }
          }
        }
      }

      // 处理剩余的缓冲区
      if (buffer.trim()) {
        const trimmedLine = buffer.trim();
        if (trimmedLine.startsWith('data:')) {
          const jsonStr = trimmedLine.slice(5).trim();

          if (jsonStr !== '[DONE]' && jsonStr) {
            try {
              const parsed = JSON.parse(jsonStr);

              if (parsed.result === false || (parsed.error && !parsed.type)) {
                throw new Error(parsed.error || 'Server returned an error');
              }

              hasReceivedValidEvent = true;
              yield parsed as T;
            } catch (e) {
              if (e instanceof Error && e.message) {
                throw e;
              }
              console.warn('[API Stream] Failed to parse final SSE event:', jsonStr, e);
            }
          }
        }
      }

      if (!hasReceivedValidEvent) {
        throw new Error('未收到有效的 AI 响应');
      }

      return;
    } catch (error) {
      console.error('[API Stream] Tauri streaming error:', error);
      throw error;
    }
  }

  const response = await tauriFetch(targetUrl, config);

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

  const decoder = new TextDecoder();
  let buffer = '';
  let hasReceivedValidEvent = false;

  try {
    while (true) {
      const { done, value } = await reader.read();

      if (done) break;

      buffer += decoder.decode(value, { stream: true });

      // 按行分割处理 SSE 数据
      const lines = buffer.split('\n');
      buffer = lines.pop() || ''; // 保留最后一个不完整的行

      for (const line of lines) {
        const trimmedLine = line.trim();

        // 跳过空行和注释
        if (!trimmedLine || trimmedLine.startsWith(':')) continue;

        // 解析 SSE 数据行
        if (trimmedLine.startsWith('data:')) {
          const jsonStr = trimmedLine.slice(5).trim();

          // 跳过 [DONE] 标记
          if (jsonStr === '[DONE]') {
            continue;
          }

          if (jsonStr) {
            try {
              const parsed = JSON.parse(jsonStr);

              // 检查是否是错误响应格式 (result: false 或有 error 字段)
              if (parsed.result === false || (parsed.error && !parsed.type) || parsed.type === 'ERROR' || parsed.type === 'RUN_ERROR') {
                throw new Error(parsed.error || parsed.message || 'Server returned an error');
              }

              // 正常的事件
              hasReceivedValidEvent = true;
              yield parsed as T;
            } catch (e) {
              // 如果是我们自己抛出的 Error，继续向上抛出
              if (e instanceof Error && e.message) {
                throw e;
              }
              console.warn('[API Stream Browser] ❌ Failed to parse SSE event:', jsonStr, e);
            }
          }
        } else {
          console.warn('[API Stream Browser] ⚠️ Line does not start with "data:":', trimmedLine.substring(0, 100));
        }
      }
    }

    // 处理剩余的缓冲区
    if (buffer.trim()) {
      const trimmedLine = buffer.trim();
      if (trimmedLine.startsWith('data:')) {
        const jsonStr = trimmedLine.slice(5).trim();

        // 跳过 [DONE] 标记
        if (jsonStr === '[DONE]') {
          // do nothing
        } else if (jsonStr) {
          try {
            const parsed = JSON.parse(jsonStr);

            // 检查是否是错误响应格式
            if (parsed.result === false || (parsed.error && !parsed.type)) {
              throw new Error(parsed.error || 'Server returned an error');
            }

            hasReceivedValidEvent = true;
            yield parsed as T;
          } catch (e) {
            if (e instanceof Error && e.message) {
              throw e;
            }
            console.warn('Failed to parse final SSE event:', jsonStr, e);
          }
        }
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
