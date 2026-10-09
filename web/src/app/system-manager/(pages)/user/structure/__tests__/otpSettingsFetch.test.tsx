import React from 'react';
import '@ant-design/v5-patch-for-react-19';
import { act, cleanup, render } from '@testing-library/react';
import { IntlProvider } from 'react-intl';
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';

const getMock = vi.hoisted(() => vi.fn());

vi.mock('@/utils/request', () => ({
  default: () => ({
    get: getMock,
    post: vi.fn(),
  }),
  isSilentRequestError: () => false,
}));

vi.mock('@/context/client', () => ({
  useClientData: () => ({ clientData: [] }),
}));

vi.mock('@/context/userInfo', () => ({
  useUserInfoContext: () => ({ refreshUserInfo: vi.fn() }),
}));

vi.mock('next-auth/react', () => ({
  useSession: () => ({ data: null, status: 'unauthenticated', update: vi.fn() }),
}));

vi.mock('next/navigation', () => ({
  usePathname: () => '/system-manager/user/structure',
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}));

import UserStructurePage from '../page';

const SYS_SET = '/system_mgmt/system_settings/get_sys_set/';

beforeAll(() => {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: (query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: () => undefined,
      removeListener: () => undefined,
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
      dispatchEvent: () => false,
    }),
  });
});

afterEach(() => {
  cleanup();
  getMock.mockReset();
});

const sysSetCalls = () => getMock.mock.calls.filter((call) => call[0] === SYS_SET).length;

describe('组织架构页加载系统配置', () => {
  it('进入页面只请求一次 get_sys_set，后续渲染不再请求', async () => {
    getMock.mockImplementation(async (url: string) => {
      if (url === SYS_SET) {
        return { enable_otp: '0' };
      }
      if (String(url).includes('search_group_list')) {
        return [];
      }
      return { items: [], count: 0 };
    });

    const view = render(
      <IntlProvider locale="zh" messages={{}}>
        <UserStructurePage />
      </IntlProvider>,
    );

    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 50));
    });
    expect(sysSetCalls()).toBe(1);

    view.rerender(
      <IntlProvider locale="zh" messages={{}}>
        <UserStructurePage />
      </IntlProvider>,
    );
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 50));
    });
    view.unmount();

    expect(sysSetCalls()).toBe(1);
  });
});
