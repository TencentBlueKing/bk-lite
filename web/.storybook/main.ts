import type { StorybookConfig } from '@storybook/nextjs';
import path from 'path';
import { fileURLToPath } from 'url';
import { createRequire } from 'module';

const storybookDir = path.dirname(fileURLToPath(import.meta.url));
// 仪表盘 story 的无后端替身与 stories 放在一起，便于统一维护。
const mocksDir = path.resolve(storybookDir, '../src/app/monitor/dashboards/stories/mocks');
const mock = (file: string) => path.resolve(mocksDir, file);

// webpack 是 storybook builder 的传递依赖，pnpm 下顶层不可见；
// 从 builder-webpack5 的位置解析它。
const require = createRequire(import.meta.url);
const builderEntry = require.resolve('@storybook/builder-webpack5/package.json');
const webpack = require(
  require.resolve('webpack', { paths: [path.dirname(builderEntry)] })
);

const config: StorybookConfig = {
  stories: ['../src/**/*.mdx', '../src/**/*.stories.@(js|jsx|mjs|ts|tsx)'],
  addons: [],
  framework: {
    name: '@storybook/nextjs',
    options: {},
  },
  staticDirs: ['../public'],
  webpackFinal: async (config) => {
    if (config.resolve) {
      config.resolve.alias = {
        '@/context/auth': mock('auth.tsx'),
        ...config.resolve.alias,
      };
    }
    // 无后端预览：在「模块解析后」用替身替换真实取数模块。
    // 用 NormalModuleReplacementPlugin 而非 alias —— tsconfig-paths 插件会先于
    // alias 把 '@/...' 解析到 src 真实文件，只有按解析后的绝对路径拦截才稳妥。
    // 回调形式同时改写 context，否则替身内的相对 import 会按原文件目录解析。
    const replace = (regex: RegExp, file: string) =>
      new webpack.NormalModuleReplacementPlugin(regex, (result: { request: string; context: string }) => {
        result.request = mock(file);
        result.context = mocksDir;
      });
    config.plugins = config.plugins || [];
    config.plugins.push(
      replace(/[\\/]app[\\/]monitor[\\/]api[\\/]view(\.tsx?)?$/, 'monitor-view-api.tsx'),
      replace(/[\\/]app[\\/]monitor[\\/]api[\\/]index(\.tsx?)?$/, 'monitor-api.tsx')
    );
    return config;
  },
};
export default config;
