const isProd = process.env.NODE_ENV === 'production';

const internalHost = process.env.TAURI_DEV_HOST || 'localhost';
const rawBasePath = process.env.NEXT_PUBLIC_BASE_PATH || (process.env.BK_MOBILE_TARGET === 'h5' ? '/mobile/h5' : '');
const basePath = rawBasePath ? `/${rawBasePath.replace(/^\/|\/$/g, '')}` : '';

const rawDevProxyTarget = !isProd ? 'http://127.0.0.1:8011' : '';
const devProxyTarget = rawDevProxyTarget.replace(/\/$/, '');

const devRewrites = !isProd && devProxyTarget ? {
  async rewrites() {
    return [
      {
        source: '/api/proxy/:path*',
        destination: `${devProxyTarget}/api/v1/:path*/`,
      },
    ];
  },
} : {};

/** @type {import('next').NextConfig} */
const nextConfig = {
  output: isProd ? 'export' : undefined,
  basePath: isProd && basePath ? basePath : undefined,

  images: {
    unoptimized: true,
  },

  assetPrefix: isProd ? (basePath || undefined) : (
    process.env.TAURI_DEV === 'true' ? `http://${internalHost}:3001` : undefined
  ),

  ...devRewrites,

  reactStrictMode: false,
};

export default nextConfig;
