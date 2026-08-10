import fs from 'fs';
import path from 'path';
import withBundleAnalyzer from '@next/bundle-analyzer';

const enterpriseWebLink = path.resolve(process.cwd(), 'enterprise');
const enterpriseWebRoot = fs.existsSync(enterpriseWebLink) ? fs.realpathSync(enterpriseWebLink) : '';
const repositoryRoot = path.resolve(process.cwd(), '..');

// Local enterprise layout keeps WeOpsX-Enterprise as a sibling of bk-lite.
// Turbopack/file tracing must cover that realpath, not only the BK-Lite repo root.
function commonFilesystemRoot(left, right) {
  const leftParts = path.resolve(left).split(path.sep);
  const rightParts = path.resolve(right).split(path.sep);
  const shared = [];
  for (let i = 0; i < Math.min(leftParts.length, rightParts.length); i += 1) {
    if (leftParts[i] !== rightParts[i]) {
      break;
    }
    shared.push(leftParts[i]);
  }
  return shared.length > 1 ? shared.join(path.sep) : path.sep;
}

const workspaceRoot = enterpriseWebRoot
  ? commonFilesystemRoot(repositoryRoot, enterpriseWebRoot)
  : undefined;

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
  outputFileTracingRoot: workspaceRoot,
  turbopack: workspaceRoot
    ? { root: workspaceRoot }
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
