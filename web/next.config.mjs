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

const webchatUiEmbed = path.resolve(repositoryRoot, 'webchat/packages/webchat-ui/src/embed.ts');
const webchatCoreSrc = path.resolve(repositoryRoot, 'webchat/packages/webchat-core/src/index.ts');
const hasWebchatSource = fs.existsSync(webchatUiEmbed);

// Turbopack treats alias values starting with `/` as server-relative to `turbopack.root`,
// not filesystem paths. Keep webpack on absolute paths; give Turbopack cwd-relative ones.
function toTurbopackAlias(absolutePath) {
  const relative = path.relative(process.cwd(), absolutePath).split(path.sep).join('/');
  return relative.startsWith('.') ? relative : `./${relative}`;
}

const webpackWebchatAliases = hasWebchatSource
  ? {
      '@webchat/ui': webchatUiEmbed,
      '@webchat/core': webchatCoreSrc,
    }
  : undefined;
const turbopackWebchatAliases = hasWebchatSource
  ? Object.fromEntries(
      Object.entries(webpackWebchatAliases).map(([key, absolutePath]) => [
        key,
        toTurbopackAlias(absolutePath),
      ])
    )
  : undefined;
const turbopackRoot = workspaceRoot;

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
  transpilePackages: ['@antv/g6', '@antv/xflow', '@webchat/ui', '@webchat/core', '@ag-ui/core'],
  typescript: {
    tsconfigPath: 'tsconfig.build.json',
  },
  outputFileTracingRoot: workspaceRoot,
  turbopack: (turbopackRoot || turbopackWebchatAliases)
    ? {
        ...(turbopackRoot ? { root: turbopackRoot } : {}),
        ...(turbopackWebchatAliases ? { resolveAlias: turbopackWebchatAliases } : {}),
      }
    : undefined,
  webpack: (config) => {
    if (webpackWebchatAliases) {
      config.resolve.alias = {
        ...config.resolve.alias,
        ...webpackWebchatAliases,
      };
    }
    return config;
  },
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
