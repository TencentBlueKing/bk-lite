/**
 * API 客户端工具
 * 所有请求统一通过 Tauri Rust 后端转发
 */

import { tauriFetch, getApiBaseUrl } from '../utils/tauriFetch';

const API_BASE_URL = getApiBaseUrl();

/**
 * 创建带有默认配置的请求（统一使用 Tauri 转发）
 */
export async function apiRequest<T = any>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const url = `${API_BASE_URL}${endpoint}`;

  // 从 localStorage 获取 token
  const token = typeof window !== 'undefined' ? localStorage.getItem('token') : null;

  // 合并默认配置
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
    const response = await tauriFetch(url, config);

    // 检查响应状态
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
    // If the request was aborted, don't log a noisy error in the console.
    // Let callers handle AbortError as needed.
    if (error && (error.name === 'AbortError')) {
      throw error;
    }

    console.error('[API] Request failed:', url, error);
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

// 导出 API 基础 URL 供其他模块使用
export { API_BASE_URL, getApiBaseUrl };
