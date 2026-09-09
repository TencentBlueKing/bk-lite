import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { IntlProvider } from 'react-intl';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { requestLegacyThirdLoginAuthorize } = vi.hoisted(() => ({
  requestLegacyThirdLoginAuthorize: vi.fn(),
}));

vi.mock('@/utils/legacyThirdLogin', () => ({
  requestLegacyThirdLoginAuthorize,
}));

vi.mock('@/hooks/usePortalBranding', () => ({
  usePortalBranding: () => ({
    logoUrl: '/logo-site.png',
    portalName: 'BlueKing Lite',
  }),
}));

vi.mock('../login-auth/SigninLanguageToggle', () => ({
  default: () => <div>language-toggle</div>,
}));

import LegacyThirdLoginAuthorizeBridge from '../LegacyThirdLoginAuthorizeBridge';
import { PORTAL_HOME_PATH } from '@/utils/route';

const messages = {
  'signin.legacyThirdLogin.title': '登录成功',
  'signin.legacyThirdLogin.returning': '正在返回原页面...',
  'signin.legacyThirdLogin.continue': '手动继续',
};

const renderBridge = () => render(
  <IntlProvider locale="zh" messages={messages} onError={() => undefined}>
    <LegacyThirdLoginAuthorizeBridge
      callbackUrl="https://example.test/playground?third_login_code=legacy-code"
      thirdLoginCode="legacy-code"
      token="jwt-token"
    />
  </IntlProvider>,
);

describe('LegacyThirdLoginAuthorizeBridge', () => {
  const locationReplace = vi.fn();

  beforeEach(() => {
    vi.useFakeTimers();
    requestLegacyThirdLoginAuthorize.mockReset();
    locationReplace.mockReset();
    vi.stubGlobal('location', {
      replace: locationReplace,
      href: 'http://localhost/auth/signin',
    });
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  it('reuses the login page frame while handing off', () => {
    requestLegacyThirdLoginAuthorize.mockReturnValue(new Promise(() => undefined));
    const { container } = renderBridge();

    expect(screen.getByRole('heading', { level: 2, name: '登录成功' })).toBeTruthy();
    expect(screen.getByText('正在返回原页面...')).toBeTruthy();
    expect(container.querySelector('aside')?.getAttribute('style')).toContain(
      'system-login-bg-plain.jpg',
    );
    expect(screen.queryByRole('button', { name: '手动继续' })).toBeNull();
  });

  it('shows a manual continue control if authorize is still pending after 3s', async () => {
    requestLegacyThirdLoginAuthorize.mockReturnValue(new Promise(() => undefined));
    renderBridge();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(3000);
    });

    fireEvent.click(screen.getByRole('button', { name: '手动继续' }));
    expect(locationReplace).toHaveBeenCalledWith(PORTAL_HOME_PATH);
  });

  it('redirects to the authorized callback when authorize resolves', async () => {
    requestLegacyThirdLoginAuthorize.mockResolvedValue('https://example.test/playground?bk_lite_code=one-time');
    renderBridge();

    await act(async () => {
      await Promise.resolve();
    });

    expect(locationReplace).toHaveBeenCalledWith(
      'https://example.test/playground?bk_lite_code=one-time',
    );
  });
});
