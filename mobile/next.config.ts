const isProd = process.env.NODE_ENV === 'production';

const internalHost = process.env.TAURI_DEV_HOST || 'localhost';

/** @type {import('next').NextConfig} */
const nextConfig = {
  // 生产环境使用静态导出
  output: isProd ? 'export' : undefined,

  images: {
    unoptimized: true,
  },

  // Tauri 开发模式：使用内部主机
  // 浏览器开发模式：不设置 assetPrefix
  assetPrefix: isProd ? undefined : (
    process.env.TAURI_DEV === 'true' ? `http://${internalHost}:3001` : undefined
  ),

  // 禁用严格模式以避免 Tauri API 初始化问题
  reactStrictMode: false,

  // 开发环境代理配置（生产环境自动忽略）
  async rewrites() {
    // 生产环境（静态导出）不需要 rewrites
    if (isProd) return [];

    const apiTarget = process.env.NEXTAPI_URL || 'https://bklite.canway.net';

    console.log('[Next.js Rewrites] Proxying /dev-proxy/* to', apiTarget);

    return [
      {
        source: '/dev-proxy/:path(.*)',
        destination: `${apiTarget}/:path`,
      },
    ];
  },
};

export default nextConfig;