import fs from 'fs';
import path from 'path';
import withBundleAnalyzer from '@next/bundle-analyzer';

const enterpriseWebLink = path.resolve(process.cwd(), 'enterprise');
const enterpriseWebRoot = fs.existsSync(enterpriseWebLink) ? fs.realpathSync(enterpriseWebLink) : '';
const repositoryRoot = path.resolve(process.cwd(), '..');

const nextConfig = withBundleAnalyzer({
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
  typescript: {
    tsconfigPath: 'tsconfig.build.json',
  },
  outputFileTracingRoot: enterpriseWebRoot
    ? repositoryRoot
    : undefined,
  turbopack: enterpriseWebRoot
    ? { root: repositoryRoot }
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
});

export default nextConfig;
