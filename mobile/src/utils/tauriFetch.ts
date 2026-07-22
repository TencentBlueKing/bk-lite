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
    return tauriApiFetch(url, options);
  }

  return fetch(url, options);
}
