const rawBasePath = process.env.NEXT_PUBLIC_BASE_PATH || '';
const appBasePath = rawBasePath ? `/${rawBasePath.replace(/^\/|\/$/g, '')}` : '';

export function withBasePath(path: string): string {
  const normalizedPath = path.startsWith('/') ? path : `/${path}`;
  return appBasePath ? `${appBasePath}${normalizedPath}` : normalizedPath;
}
