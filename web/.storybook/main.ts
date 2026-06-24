import type { StorybookConfig } from '@storybook/nextjs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

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
        ...config.resolve.alias,
        '@/context/auth': path.resolve(__dirname, './mocks/auth.tsx'),
        '@/context/client': path.resolve(__dirname, './mocks/client.tsx'),
        '@/app/system-manager/api/application': path.resolve(__dirname, './mocks/system-manager/application-api.ts'),
        '@/app/system-manager/api/application/index': path.resolve(__dirname, './mocks/system-manager/application-api.ts'),
        '@/app/system-manager/api/security': path.resolve(__dirname, './mocks/system-manager/security-api.ts'),
        '@/app/system-manager/api/security/index': path.resolve(__dirname, './mocks/system-manager/security-api.ts'),
        '@/app/system-manager/api/group': path.resolve(__dirname, './mocks/system-manager/group-api.ts'),
        '@/app/system-manager/api/group/index': path.resolve(__dirname, './mocks/system-manager/group-api.ts'),
        '@/app/system-manager/api/user': path.resolve(__dirname, './mocks/system-manager/user-api.ts'),
        '@/app/system-manager/api/user/index': path.resolve(__dirname, './mocks/system-manager/user-api.ts'),
        '@/app/opspilot/api/provider': path.resolve(__dirname, './mocks/opspilot/provider-api.ts'),
        '@/app/opspilot/api/wiki': path.resolve(__dirname, './mocks/opspilot/wiki-api.ts'),
      };
    }
    return config;
  },
};
export default config;
