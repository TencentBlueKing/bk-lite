import type { Preview } from '@storybook/react';
import '@/styles/globals.css';
import Script from 'next/script';
import { AntdRegistry } from '@ant-design/nextjs-registry';
import React from 'react';
import { IntlProvider } from 'react-intl';
import { SessionProvider } from 'next-auth/react';
import { LocaleProvider } from '@/context/locale';
import { STORYBOOK_ZH_MESSAGES } from '../src/app/monitor/dashboards/stories/mocks/locale-messages';
import { ThemeProvider } from '@/context/theme';
import { ClientProvider } from '@/context/client';
import { PermissionsProvider } from '@/context/permissions';
import { UserInfoProvider } from '@/context/userInfo';
import AuthProvider from '@/context/auth';

const mockSession = {
  username: 'umr',
  expires: '3023-12-31T23:59:59.999Z',
  user: {
    id: '1',
    username: 'admin',
    email: 'admin@example.com',
  },
};

const preview: Preview = {
  decorators: [
    (Story) => (
      <SessionProvider session={mockSession}>
        <Script src="/iconfont.js" strategy="afterInteractive" />
        <LocaleProvider>
          {/* 直接提供真实中文语言包，覆盖 LocaleProvider 无后端时的空 messages，
              使 Storybook 文案（如「最近15分钟」）与实际环境一致。 */}
          <IntlProvider locale="zh" messages={STORYBOOK_ZH_MESSAGES}>
            <ThemeProvider>
              <AuthProvider>
                <UserInfoProvider>
                  <ClientProvider>
                    <PermissionsProvider>
                      <AntdRegistry>
                        <Story />
                      </AntdRegistry>
                    </PermissionsProvider>
                  </ClientProvider>
                </UserInfoProvider>
              </AuthProvider>
            </ThemeProvider>
          </IntlProvider>
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
