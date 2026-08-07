import { tauriFetch } from '@/utils/tauriFetch';

const WEB_ORIGIN = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, '') || '';

export async function fetchWebJson<T>(path: string): Promise<T> {
  const normalizedPath = path.startsWith('/') ? path : `/${path}`;
  const response = await tauriFetch(`${WEB_ORIGIN}${normalizedPath}`, {
    method: 'GET',
    credentials: 'include',
    headers: { Accept: 'application/json' },
  });
  if (!response.ok) {
    throw new Error(`Web request failed: ${response.status}`);
  }
  return response.json() as Promise<T>;
}
