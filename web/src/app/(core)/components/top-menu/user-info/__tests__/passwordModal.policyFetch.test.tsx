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
}));

import PasswordModal from '../passwordModal';

const SETTINGS = {
  pwd_set_min_length: '8',
  pwd_set_max_length: '20',
  pwd_set_required_char_types: 'uppercase,lowercase,digit,special',
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

afterEach(() => {
  cleanup();
  getMock.mockReset();
});

describe('控制台修改密码弹窗拉取密码策略', () => {
  it('打开后只请求一次 get_sys_set，保持打开不再请求', async () => {
    let calls = 0;
    getMock.mockImplementation(async (url: string) => {
      expect(url).toBe('/system_mgmt/system_settings/get_sys_set/');
      calls += 1;
      if (calls > 3) {
        return new Promise(() => undefined);
      }
      return { ...SETTINGS };
    });

    const view = render(
      <IntlProvider locale="zh" messages={{}}>
        <PasswordModal visible onCancel={() => undefined} onSuccess={() => undefined} />
      </IntlProvider>,
    );

    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 50));
    });

    expect(calls).toBe(1);

    view.rerender(
      <IntlProvider locale="zh" messages={{}}>
        <PasswordModal visible onCancel={() => undefined} onSuccess={() => undefined} />
      </IntlProvider>,
    );
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 50));
    });
    expect(calls).toBe(1);

    view.rerender(
      <IntlProvider locale="zh" messages={{}}>
        <PasswordModal visible={false} onCancel={() => undefined} onSuccess={() => undefined} />
      </IntlProvider>,
    );
    view.rerender(
      <IntlProvider locale="zh" messages={{}}>
        <PasswordModal visible onCancel={() => undefined} onSuccess={() => undefined} />
      </IntlProvider>,
    );
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 50));
    });
    view.unmount();

    expect(calls).toBe(2);
  });
});
