const isProduction = process.env.NODE_ENV === 'production';
const buildTarget = process.env.BK_MOBILE_BUILD_TARGET;
const configuredBasePath = process.env.NEXT_PUBLIC_BASE_PATH;

const H5_BASE_PATH = '/mobile/h5';
const DEFAULT_DEV_SERVER_URL = 'http://127.0.0.1:8011';
const DEFAULT_DEV_WEB_URL = 'http://127.0.0.1:3000';

function normalizeBasePath(value: string | undefined) {
  if (!value) return '';
  return `/${value.replace(/^\/|\/$/g, '')}`;
}

function normalizeOrigin(value: string) {
  return value.replace(/\/$/, '');
}

function validateProductionBuild() {
  if (!isProduction) return;
  if (buildTarget !== 'h5' && buildTarget !== 'tauri') {
    throw new Error('生产构建必须通过 build:h5 或 build:tauri 指定目标');
  }
  if (configuredBasePath === undefined) {
    throw new Error('构建脚本未注入 NEXT_PUBLIC_BASE_PATH');
  }
  if (buildTarget === 'h5' && configuredBasePath !== H5_BASE_PATH) {
    throw new Error(`H5 构建路径必须为 ${H5_BASE_PATH}`);
  }
  if (buildTarget === 'tauri' && configuredBasePath !== '') {
    throw new Error('Tauri 构建不能配置 basePath');
  }
}

validateProductionBuild();

const basePath = normalizeBasePath(configuredBasePath);
const devProxyTarget = normalizeOrigin(
  process.env.BK_SERVER_DEV_URL ?? DEFAULT_DEV_SERVER_URL,
);
const devAuthProxyTarget = normalizeOrigin(
  process.env.BK_WEB_DEV_URL ?? DEFAULT_DEV_WEB_URL,
);
const tauriDevHost = process.env.TAURI_DEV_HOST;

const devRewrites = !isProduction ? {
  async rewrites() {
    return [
      {
        source: '/api/proxy/:path*',
        destination: `${devProxyTarget}/api/v1/:path*/`,
      },
      {
        source: '/api/auth/:path*',
        destination: `${devAuthProxyTarget}/api/auth/:path*`,
      },
    ];
  },
} : {};

/** @type {import('next').NextConfig} */
const nextConfig = {
  output: isProduction ? 'export' : undefined,
  basePath: isProduction && basePath !== '' ? basePath : undefined,

  images: {
    unoptimized: true,
  },

  assetPrefix: isProduction
    ? (basePath === '' ? undefined : basePath)
    : (tauriDevHost ? `http://${tauriDevHost}:3001` : undefined),

  ...devRewrites,

  reactStrictMode: false,
};

export default nextConfig;
