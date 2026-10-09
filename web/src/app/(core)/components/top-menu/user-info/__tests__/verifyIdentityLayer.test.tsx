import React from 'react';
import '@ant-design/v5-patch-for-react-19';
import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { IntlProvider } from 'react-intl';
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';

vi.mock('@/utils/request', () => ({
  default: () => ({
    get: vi.fn(),
    post: vi.fn(),
  }),
}));

vi.mock('@/context/client', () => ({
  useClientData: () => ({ clientData: [] }),
}));

vi.mock('@/context/userInfo', () => ({
  useUserInfoContext: () => ({ refreshUserInfo: vi.fn() }),
}));

vi.mock('@/context/locale', () => ({
  useLocale: () => ({ setLocale: vi.fn() }),
}));

vi.mock('next-auth/react', () => ({
  useSession: () => ({ data: null, update: vi.fn() }),
}));

import UserInformation from '../userInformation';

const messages = {
  'userInfo.changePassword': '修改密码',
  'userInfo.verifyIdentity': '验证身份',
};

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

afterEach(cleanup);

const popupZIndex = (node: Element | null) => {
  let current = node as HTMLElement | null;
  while (current) {
    const value = Number(current.style.zIndex || getComputedStyle(current).zIndex);
    if (Number.isFinite(value) && value > 0) {
      return value;
    }
    current = current.parentElement;
  }
  return 0;
};

describe('用户信息抽屉上的验证身份弹窗', () => {
  it('打开后盖住用户信息抽屉', async () => {
    const user = userEvent.setup();
    render(
      <IntlProvider locale="zh" messages={messages}>
        <UserInformation
          visible
          onClose={() => undefined}
          fetchUserInfoAction={async () => ({
            username: 'admin',
            display_name: 'admin',
            email: 'admin@example.com',
            timezone: 'Asia/Shanghai',
            locale: 'zh-Hans',
          })}
        />
      </IntlProvider>,
    );

    await user.click(await screen.findByRole('button', { name: '修改密码' }));

    const dialog = (await screen.findByText('验证身份')).closest('[role="dialog"]');
    const drawer = document.querySelector('.ant-drawer');

    expect(popupZIndex(dialog)).toBeGreaterThan(popupZIndex(drawer));
  });
});
