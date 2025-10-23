/**
 * Tauri HTTP 客户端封装
 * 统一所有 HTTP 请求入口，优先使用 Tauri Rust 后端代理
 */

import { tauriApiFetch } from './tauriApiProxy';

/**
 * 检查是否在 Tauri 环境中
 * 
 * Tauri 2.x 使用 __TAURI_INTERNALS__ 作为主要标识
 * __TAURI__ 可能在某些版本中不存在
 */
export function isTauriApp(): boolean {
  if (typeof window === 'undefined') return false;

  // Tauri 2.x 优先检查 __TAURI_INTERNALS__
  // 这是 Tauri 运行时的核心标识
  return '__TAURI_INTERNALS__' in window;
}

/**
 * 统一的 fetch 接口 - 所有 API 请求都通过这里
 * 优先级: Tauri Rust 代理 > 标准 fetch
 */
export async function tauriFetch(
  url: string,
  options: RequestInit = {}
): Promise<Response> {
  // 1. 首选：使用 Tauri Rust 后端 API 代理
  if (isTauriApp()) {
    try {
      return await tauriApiFetch(url, options);
    } catch (error) {
      // 降级到标准 fetch
      console.warn('[TauriFetch] Rust proxy failed, falling back to standard fetch:', error);
    }
  }

  // 2. 降级：使用标准 fetch（浏览器环境会使用 Next.js 代理）
  return await fetch(url, options);
}

/**
 * 获取适合当前环境的 API 基础 URL
 */
export function getApiBaseUrl(): string {
  // Tauri 环境：直接使用 API 地址
  if (isTauriApp()) {
    return process.env.NEXTAPI_URL || 'https://bklite.canway.net';
  }

  // 浏览器开发环境：使用代理避免 CORS
  if (process.env.NODE_ENV === 'development' && typeof window !== 'undefined') {
    return '/dev-proxy';
  }

  // 浏览器生产环境：直接使用 API 地址
  return process.env.NEXTAPI_URL || 'https://bklite.canway.net';
}
