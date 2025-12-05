import { tauriApiFetch } from './tauriApiProxy';

export function isTauriApp(): boolean {
  if (typeof window === 'undefined') return false;
  return '__TAURI_INTERNALS__' in window;
}

export async function tauriFetch(
  url: string,
  options: RequestInit = {}
): Promise<Response> {
  if (isTauriApp()) {
    try {
      return await tauriApiFetch(url, options);
    } catch (error) {
      console.warn('[TauriFetch] Rust proxy failed, falling back to standard fetch:', error);
    }
  }

  return await fetch(url, options);
}
