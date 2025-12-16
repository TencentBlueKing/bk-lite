const isProd = process.env.NODE_ENV === 'production';

const internalHost = process.env.TAURI_DEV_HOST || 'localhost';

/** @type {import('next').NextConfig} */
const nextConfig = {
  output: isProd ? 'export' : undefined,

  images: {
    unoptimized: true,
  },

  assetPrefix: isProd ? undefined : (
    process.env.TAURI_DEV === 'true' ? `http://${internalHost}:3001` : undefined
  ),

  reactStrictMode: false,
};

export default nextConfig;