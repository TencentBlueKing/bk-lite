import withBundleAnalyzer from '@next/bundle-analyzer';
import { combineLocales, combineMenus, copyPublicDirectories } from './src/utils/dynamicsMerged.mjs';

let hasCombinedLocalesAndMenus = false;
let hasCopiedPublicDirs = false;

const withCombineLocalesAndMenus = (nextConfig = {}) => {
  return {
    ...nextConfig,
    webpack(config, { isServer, dev }) {
      if (!dev && isServer && !hasCombinedLocalesAndMenus) {
        config.plugins.push({
          apply: (compiler) => {
            compiler.hooks.beforeCompile.tapPromise('CombineLocalesAndMenusPlugin', async (compilation) => {
              if (!hasCombinedLocalesAndMenus) {
                await combineLocales();
                await combineMenus();
                hasCombinedLocalesAndMenus = true;
              }
            });
          },
        });
      }

      if (typeof nextConfig.webpack === 'function') {
        return nextConfig.webpack(config, { isServer, dev });
      }

      return config;
    },
  };
};

const withCopyPublicDirs = (nextConfig = {}) => {
  return {
    ...nextConfig,
    webpack(config, { isServer, dev }) {
      if (!hasCopiedPublicDirs) {
        config.plugins.push({
          apply: (compiler) => {
            compiler.hooks.beforeCompile.tapPromise('CopyPublicDirsPlugin', async (compilation) => {
              if (!hasCopiedPublicDirs) {
                copyPublicDirectories();
                hasCopiedPublicDirs = true;
              }
            });
          },
        });
      }

      if (typeof nextConfig.webpack === 'function') {
        return nextConfig.webpack(config, { isServer, dev });
      }

      return config;
    },
  };
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
      experimental: {
        turbopackCss: true,
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
