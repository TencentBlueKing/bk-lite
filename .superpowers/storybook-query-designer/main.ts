import type { StorybookConfig } from '@storybook/nextjs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const webRoot = path.resolve(__dirname, '../../web');

const config: StorybookConfig = {
  stories: [path.join(webRoot, 'src/stories/monitor-policy-query-designer.stories.tsx')],
  addons: [],
  framework: {
    name: '@storybook/nextjs',
    options: {},
  },
  staticDirs: [path.join(webRoot, 'public')],
  webpackFinal: async (config) => {
    if (config.resolve) {
      config.resolve.alias = {
        ...(config.resolve.alias as Record<string, string>),
        '@': path.join(webRoot, 'src'),
      };
    }
    return config;
  },
};

export default config;

