import type { Preview } from '@storybook/react';
import '@/styles/globals.css';
import Script from 'next/script';
import { AntdRegistry } from '@ant-design/nextjs-registry';
import React from 'react';
import { SessionProvider } from 'next-auth/react';
import { LocaleProvider } from '@/context/locale';
import { ThemeProvider } from '@/context/theme';
import { ClientProvider } from '@/context/client';
import { PermissionsProvider } from '@/context/permissions';
import { UserInfoProvider } from '@/context/userInfo';
import AuthProvider from '@/context/auth';
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

const preview: Preview = {
  decorators: [
    (Story) => (
      <SessionProvider session={mockSession}>
        <Script src="/iconfont.js" strategy="afterInteractive" />
        <LocaleProvider>
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
