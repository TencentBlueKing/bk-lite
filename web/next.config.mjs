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
// 企业版若在仓库内（submodule / junction），common root 就是仓库根。
// 此时把 turbopack.root 抬到仓库根，PostCSS 会从仓库根 resolve 插件，
// 找不到 web/node_modules 里的 @tailwindcss/postcss。
// 仅当企业版源码在仓库外（兄弟目录）时才抬升 Turbopack 根。
const enterpriseLivesOutsideRepo = Boolean(
  workspaceRoot && path.resolve(workspaceRoot) !== path.resolve(repositoryRoot)
);
const turbopackRoot = enterpriseLivesOutsideRepo ? workspaceRoot : undefined;

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
  transpilePackages: ['@antv/g6', '@antv/xflow'],
  typescript: {
    tsconfigPath: 'tsconfig.build.json',
  },
  outputFileTracingRoot: workspaceRoot,
  turbopack: turbopackRoot ? { root: turbopackRoot } : undefined,
  experimental: {
    externalDir: true,
    // 16.0.x 稳定版仅允许 Dev 缓存；ForBuild 需 canary / ≥16.3 才可显式开启
    turbopackFileSystemCacheForDev: true,
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
