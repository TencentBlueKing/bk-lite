import type { StorybookConfig } from '@storybook/nextjs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const mockAliases = [
  { name: '@/context/auth', alias: path.resolve(__dirname, './mocks/auth.tsx'), onlyModule: true },
  { name: '@/context/client', alias: path.resolve(__dirname, './mocks/client.tsx'), onlyModule: true },
  { name: '@/utils/request', alias: path.resolve(__dirname, './mocks/monitor-dashboard-request.ts'), onlyModule: true },
  { name: '@/app/system-manager/api/application', alias: path.resolve(__dirname, './mocks/system-manager/application-api.ts'), onlyModule: true },
  { name: '@/app/system-manager/api/application/index', alias: path.resolve(__dirname, './mocks/system-manager/application-api.ts'), onlyModule: true },
  { name: '@/app/system-manager/api/security', alias: path.resolve(__dirname, './mocks/system-manager/security-api.ts'), onlyModule: true },
  { name: '@/app/system-manager/api/security/index', alias: path.resolve(__dirname, './mocks/system-manager/security-api.ts'), onlyModule: true },
  { name: '@/app/system-manager/api/group', alias: path.resolve(__dirname, './mocks/system-manager/group-api.ts'), onlyModule: true },
  { name: '@/app/system-manager/api/group/index', alias: path.resolve(__dirname, './mocks/system-manager/group-api.ts'), onlyModule: true },
  { name: '@/app/system-manager/api/user', alias: path.resolve(__dirname, './mocks/system-manager/user-api.ts'), onlyModule: true },
  { name: '@/app/system-manager/api/user/index', alias: path.resolve(__dirname, './mocks/system-manager/user-api.ts'), onlyModule: true },
  { name: '@/app/opspilot/api/provider', alias: path.resolve(__dirname, './mocks/opspilot/provider-api.ts'), onlyModule: true },
];

const toAliasArray = (aliases: unknown) => {
  if (Array.isArray(aliases)) return aliases;
  if (!aliases || typeof aliases !== 'object') return [];
  return Object.entries(aliases).map(([name, alias]) => ({ name, alias }));
};

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
      config.resolve.alias = [
        ...mockAliases,
        ...toAliasArray(config.resolve.alias).filter((item: any) =>
          !mockAliases.some((mock) => mock.name === item.name)
        ),
      ] as any;
    }
    return config;
  },
};
export default config;
