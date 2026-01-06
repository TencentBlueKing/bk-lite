import withBundleAnalyzer from '@next/bundle-analyzer';
import { combineLocales, combineMenus, copyPublicDirectories } from './src/utils/dynamicsMerged.mjs';

// 在模块加载时就执行准备工作
const isProduction = process.env.NODE_ENV === 'production';

// 准备构建资源
async function prepareBuildAssets() {
  console.log('🔄 Preparing build assets...');
  
  // 合并 locales 和 menus
  await combineLocales();
  await combineMenus();
  
  // 拷贝 public 目录
  copyPublicDirectories();
  
  console.log('✅ Build assets prepared successfully!');
}

// 只在生产构建时执行准备工作
if (isProduction) {
  await prepareBuildAssets();
}

const withCombineLocalesAndMenus = (nextConfig = {}) => {
  return nextConfig;
};

const withCopyPublicDirs = (nextConfig = {}) => {
  return nextConfig;
};

const nextConfig = withCombineLocalesAndMenus(
  withCopyPublicDirs(
    withBundleAnalyzer({
      enabled: process.env.ANALYZE === 'true',
    })({
      reactStrictMode: true,
      sassOptions: {
        implementation: 'sass-embedded',
      },
      staticPageGenerationTimeout: 300,
      transpilePackages: ['@antv/g6'],
      typescript: {
        ignoreBuildErrors: true,
      },
      // experimental: {
      //   proxyTimeout: 300_000, // Set timeout to 300 seconds
      // },
      // async rewrites() {
      //   return [
      //     {
      //       source: '/reqApi/:path*',
      //       destination: `${process.env.NEXTAPI_URL}/:path*/`,
      //     },
      //   ];
      // },
    })
  )
);

export default nextConfig;