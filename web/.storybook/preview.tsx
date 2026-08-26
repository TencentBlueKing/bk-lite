import type { Preview } from '@storybook/nextjs';
import '@/styles/globals.css';
import Script from 'next/script';
import { AntdRegistry } from '@ant-design/nextjs-registry';
import React from 'react';
import { IntlProvider } from 'react-intl';
import { SessionProvider } from 'next-auth/react';
import { LocaleProvider } from '@/context/locale';
import zhCommon from '@/locales/zh.json';
import zhOpspilot from '@/app/opspilot/locales/zh.json';
import { ThemeBootstrap, ThemeProvider } from '@/theme';
import { PermissionsProvider } from '@/context/permissions';
// 相对路径引入 mock；webpack 同时把 `@/context/auth` 等换成同一批文件，避免真登录壳 / 双 Context。
import AuthProvider from './mocks/auth';
import { ClientProvider } from './mocks/client';
import { UserInfoProvider } from './mocks/user-info';
import { installMonitorDashboardRequestInterceptor } from './mocks/monitor-dashboard-request';

installMonitorDashboardRequestInterceptor();

const mockSession = {
  username: 'umr',
  expires: '3023-12-31T23:59:59.999Z',
  user: {
    id: '1',
    username: 'admin',
    email: 'admin@example.com',
  },
};

// Storybook 无 /api/locales,故直接从本地 JSON 扁平化(嵌套 → 点号 key)注入消息,
// 内层 IntlProvider 覆盖 LocaleProvider 取不到时的空消息,让 t('wiki.xxx') 正常显示中文。
type LocaleJson = Record<string, unknown>;
const flatten = (obj: LocaleJson, prefix = '', out: Record<string, string> = {}) => {
  Object.keys(obj).forEach((k) => {
    const v = obj[k];
    const key = prefix ? `${prefix}.${k}` : k;
    if (v && typeof v === 'object' && !Array.isArray(v)) flatten(v as LocaleJson, key, out);
    else out[key] = String(v);
  });
  return out;
};
const sbMessages = { ...flatten(zhCommon as LocaleJson), ...flatten(zhOpspilot as LocaleJson) };

const preview: Preview = {
  decorators: [
    (Story) => (
      <SessionProvider session={mockSession}>
        <ThemeBootstrap />
        <Script src="/iconfont.js" strategy="afterInteractive" />
        <LocaleProvider>
          <ThemeProvider>
            <AuthProvider>
              <UserInfoProvider>
                <ClientProvider>
                  <PermissionsProvider>
                    <AntdRegistry>
                      {/* @ts-expect-error react-intl type incompatibility with React 19 */}
                      <IntlProvider locale="zh" messages={sbMessages}>
                        <Story />
                      </IntlProvider>
                    </AntdRegistry>
                  </PermissionsProvider>
                </ClientProvider>
              </UserInfoProvider>
            </AuthProvider>
          </ThemeProvider>
        </LocaleProvider>
      </SessionProvider>
    ),
  ],
  tags: ['autodocs'],
  parameters: {
    nextjs: {
      appDirectory: true,
      navigation: {
        pathname: '/',
      },
    },
    controls: {
      matchers: {
        color: /(background|color)$/i,
        date: /Date$/i,
      },
    },
  },
};

export default preview;
