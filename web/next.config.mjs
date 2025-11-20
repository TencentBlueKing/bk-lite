import withBundleAnalyzer from '@next/bundle-analyzer';
import { combineLocales, combineMenus, copyPublicDirectories } from './src/utils/dynamicsMerged.mjs';
import { fileURLToPath } from 'url';
import { dirname, resolve } from 'path';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

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
      
      // 性能优化配置
      swcMinify: true, // 使用 SWC 压缩
      compiler: {
        removeConsole: process.env.NODE_ENV === 'production', // 生产环境移除 console
      },
      
      // 跳过不需要编译的包
      transpilePackages: [
        'antd',
        '@ant-design/icons',
        '@ant-design/nextjs-registry',
        'react-intl',
        'intl-messageformat',
      ],
      
      // 优化 Webpack 配置
      webpack: (config, { dev, isServer }) => {
        // 生产环境优化
        if (!dev) {
          config.optimization = {
            ...config.optimization,
            moduleIds: 'deterministic',
            splitChunks: {
              chunks: 'all',
              cacheGroups: {
                default: false,
                vendors: false,
                // 框架核心
                framework: {
                  name: 'framework',
                  chunks: 'all',
                  test: /(?<!node_modules.*)[\\/]node_modules[\\/](react|react-dom|scheduler|prop-types|use-subscription)[\\/]/,
                  priority: 40,
                  enforce: true,
                },
                // Ant Design
                antd: {
                  name: 'antd',
                  test: /[\\/]node_modules[\\/](@ant-design|antd)[\\/]/,
                  priority: 30,
                },
                // 图表库
                charts: {
                  name: 'charts',
                  test: /[\\/]node_modules[\\/](@xyflow)[\\/]/,
                  priority: 25,
                },
                // 其他库
                lib: {
                  test: /[\\/]node_modules[\\/]/,
                  name(module) {
                    const packageName = module.context.match(/[\\/]node_modules[\\/](.*?)([\\/]|$)/)?.[1];
                    return `npm.${packageName?.replace('@', '')}`;
                  },
                  priority: 20,
                  minChunks: 1,
                  reuseExistingChunk: true,
                },
                // 公共组件
                commons: {
                  name: 'commons',
                  minChunks: 2,
                  priority: 10,
                  reuseExistingChunk: true,
                },
              },
            },
          };
          
          // 生产环境减少 source map 生成
          config.devtool = 'hidden-source-map';
        }
        
        // 开发环境优化
        if (dev) {
          config.devtool = 'eval-cheap-module-source-map';
        }
        
        // 缓存优化 - 使用绝对路径
        config.cache = {
          type: 'filesystem',
          cacheDirectory: resolve(__dirname, '.next/cache/webpack'),
        };
        
        // 忽略某些警告
        config.ignoreWarnings = [
          /Module not found/,
          /Critical dependency/,
        ];
        
        return config;
      },
      
      // 实验性功能
      experimental: {
        optimizePackageImports: [
          'antd',
          '@ant-design/icons',
          'lodash',
          'dayjs',
        ],
        // proxyTimeout: 300_000,
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
