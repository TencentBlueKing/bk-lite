import type { StorybookConfig } from '@storybook/nextjs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const mocks = {
  auth: path.resolve(__dirname, './mocks/auth.tsx'),
  client: path.resolve(__dirname, './mocks/client.tsx'),
  userInfo: path.resolve(__dirname, './mocks/user-info.tsx'),
  request: path.resolve(__dirname, './mocks/monitor-dashboard-request.ts'),
  applicationApi: path.resolve(__dirname, './mocks/system-manager/application-api.ts'),
  securityApi: path.resolve(__dirname, './mocks/system-manager/security-api.ts'),
  groupApi: path.resolve(__dirname, './mocks/system-manager/group-api.ts'),
  userApi: path.resolve(__dirname, './mocks/system-manager/user-api.ts'),
  providerApi: path.resolve(__dirname, './mocks/opspilot/provider-api.ts'),
  wikiApi: path.resolve(__dirname, './mocks/opspilot/wiki-api.ts'),
} as const;

/**
 * Next/Storybook 的 TsconfigPathsPlugin 会先把 `@/…` 解析到 src，webpack alias 经常失效。
 * 不用 require('webpack')：仓库里有 webpack@0.9.0，会把 main.ts 评估直接打挂。
 */
const requestReplacements: Array<{ pattern: RegExp; target: string }> = [
  { pattern: /^@\/context\/auth(\.tsx)?$/, target: mocks.auth },
  { pattern: /^@\/context\/client(\.tsx)?$/, target: mocks.client },
  { pattern: /^@\/context\/userInfo(\.tsx)?$/, target: mocks.userInfo },
  { pattern: /^@\/utils\/request(\.ts)?$/, target: mocks.request },
  { pattern: /^@\/app\/system-manager\/api\/application(\/index)?$/, target: mocks.applicationApi },
  { pattern: /^@\/app\/system-manager\/api\/security(\/index)?$/, target: mocks.securityApi },
  { pattern: /^@\/app\/system-manager\/api\/group(\/index)?$/, target: mocks.groupApi },
  { pattern: /^@\/app\/system-manager\/api\/user(\/index)?$/, target: mocks.userApi },
  { pattern: /^@\/app\/opspilot\/api\/provider$/, target: mocks.providerApi },
  { pattern: /^@\/app\/opspilot\/api\/wiki$/, target: mocks.wikiApi },
  { pattern: /[\\/]src[\\/]context[\\/]auth\.tsx$/, target: mocks.auth },
  { pattern: /[\\/]src[\\/]context[\\/]client\.tsx$/, target: mocks.client },
  { pattern: /[\\/]src[\\/]context[\\/]userInfo\.tsx$/, target: mocks.userInfo },
  { pattern: /[\\/]src[\\/]utils[\\/]request\.ts$/, target: mocks.request },
];

const mockAliasMap: Record<string, string> = {
  '@/context/auth': mocks.auth,
  '@/context/client': mocks.client,
  '@/context/userInfo': mocks.userInfo,
  '@/utils/request': mocks.request,
  '@/app/system-manager/api/application': mocks.applicationApi,
  '@/app/system-manager/api/application/index': mocks.applicationApi,
  '@/app/system-manager/api/security': mocks.securityApi,
  '@/app/system-manager/api/security/index': mocks.securityApi,
  '@/app/system-manager/api/group': mocks.groupApi,
  '@/app/system-manager/api/group/index': mocks.groupApi,
  '@/app/system-manager/api/user': mocks.userApi,
  '@/app/system-manager/api/user/index': mocks.userApi,
  '@/app/opspilot/api/provider': mocks.providerApi,
  '@/app/opspilot/api/wiki': mocks.wikiApi,
};

const toAliasObject = (aliases: unknown): Record<string, string> => {
  if (!aliases) return {};
  if (Array.isArray(aliases)) {
    return Object.fromEntries(
      aliases
        .filter((item): item is { name: string; alias: string } => Boolean(item?.name && item?.alias))
        .map((item) => [item.name, item.alias]),
    );
  }
  if (typeof aliases === 'object') {
    return Object.fromEntries(
      Object.entries(aliases as Record<string, unknown>).filter(
        (entry): entry is [string, string] => typeof entry[1] === 'string',
      ),
    );
  }
  return {};
};

class StorybookMockReplacePlugin {
  apply(compiler: { hooks: { normalModuleFactory: { tap: (name: string, fn: (nmf: any) => void) => void } } }) {
    compiler.hooks.normalModuleFactory.tap('StorybookMockReplacePlugin', (nmf) => {
      nmf.hooks.beforeResolve.tap('StorybookMockReplacePlugin', (data: { request?: string } | undefined) => {
        if (!data?.request) return;
        for (const { pattern, target } of requestReplacements) {
          if (pattern.test(data.request)) {
            data.request = target;
            return;
          }
        }
      });
    });
  }
}

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
        ...toAliasObject(config.resolve.alias),
        ...mockAliasMap,
        ...Object.fromEntries(
          Object.entries(mockAliasMap).map(([name, alias]) => [`${name}$`, alias]),
        ),
      };
    }

    config.plugins = [...(config.plugins || []), new StorybookMockReplacePlugin()];
    return config;
  },
};

export default config;
