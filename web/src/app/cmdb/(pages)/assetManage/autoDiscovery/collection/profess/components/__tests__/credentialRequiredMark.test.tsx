import React from 'react';
import '@ant-design/v5-patch-for-react-19';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, beforeAll, expect, it, vi } from 'vitest';
import CredentialPoolEditor, { type CredentialPoolEditorProps } from '../credentialPoolEditor';

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({ t: (_key: string, fallback?: string) => fallback || _key }),
}));
vi.mock('@/components/credential-picker', () => ({ default: () => <div>凭据选择</div> }));

beforeAll(() => {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: (query: string) => ({
      matches: false, media: query, onchange: null,
      addListener: () => undefined, removeListener: () => undefined,
      addEventListener: () => undefined, removeEventListener: () => undefined,
      dispatchEvent: () => false,
    }),
  });
});
afterEach(cleanup);

function expectRequired(label: string, required = true) {
  const text = screen.getByText(label);
  if (required) {
    expect(text.previousElementSibling?.textContent, `${label} 应显示必填星号`).toBe('*');
    return;
  }
  expect(text.previousElementSibling?.textContent, `${label} 不应显示必填星号`).not.toBe('*');
}

function renderShape(shape: CredentialPoolEditorProps['credentialShape'], value: Record<string, unknown> = {}) {
  render(<CredentialPoolEditor credentialShape={shape} value={[{ ...value }]} />);
}

it('SSH 用户名密码与端口均显示必填星号', () => {
  renderShape('ssh', { port: 22 });
  expectRequired('用户');
  expectRequired('密码');
  expectRequired('端口');
});

it('SQL / WinRM / 平台账户的认证字段显示必填星号', () => {
  renderShape('sql', { port: 3306 });
  expectRequired('用户');
  expectRequired('密码');
  cleanup();
  renderShape('winrm', { port: 5986, scheme: 'https' });
  expectRequired('用户');
  expectRequired('密码');
  cleanup();
  renderShape('platform_api', { port: 443 });
  expectRequired('用户');
  expectRequired('密码');
});

it('真正选填的凭据字段不显示必填星号', () => {
  renderShape('influxdb', { port: 8086, scheme: 'http' });
  expectRequired('Operator Token', false);
  cleanup();
  renderShape('macos_ssh', { port: 22, authType: 'privateKey' });
  expectRequired('用户');
  expectRequired('密码短语', false);
});
