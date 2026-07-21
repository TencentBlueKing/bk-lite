const rawBasePath = process.env.NEXT_PUBLIC_BASE_PATH || '';
export const APP_BASE_PATH = rawBasePath ? `/${rawBasePath.replace(/^\/|\/$/g, '')}` : '';

export function withBasePath(path: string): string {
  const normalizedPath = path.startsWith('/') ? path : `/${path}`;
  return APP_BASE_PATH ? `${APP_BASE_PATH}${normalizedPath}` : normalizedPath;
}
