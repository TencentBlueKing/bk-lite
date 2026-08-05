import fs from 'fs';
import path from 'path';
import withBundleAnalyzer from '@next/bundle-analyzer';
import { prepareEnterpriseRoutes } from './scripts/prepare-enterprise.mjs';
import { combineLocales, combineMenus, copyPublicDirectories } from './src/utils/dynamicsMerged.mjs';

const enterpriseWebLink = path.resolve(process.cwd(), 'enterprise');
const enterpriseWebRoot = fs.existsSync(enterpriseWebLink) ? fs.realpathSync(enterpriseWebLink) : '';

// 在模块加载时就执行准备工作
const isProduction = process.env.NODE_ENV === 'production';

// 准备构建资源
async function prepareBuildAssets() {
  console.log('🔄 Preparing build assets...');

  await prepareEnterpriseRoutes();
  
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
      allowedDevOrigins: ['bklite.weops.com'],
      env: {
        ENTERPRISE_WEB_ROOT: enterpriseWebRoot,
      },
      sassOptions: {
        implementation: 'sass-embedded',
      },
      staticPageGenerationTimeout: 300,
      transpilePackages: ['@antv/g6'],
      outputFileTracingRoot: enterpriseWebRoot
        ? path.resolve(process.cwd(), '../..')
        : undefined,
      experimental: {
        externalDir: true,
        turbopackFileSystemCacheForDev: true,
        turbopackFileSystemCacheForBuild: true,
        // proxyTimeout: 300_000, // Set timeout to 300 seconds
      },
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
