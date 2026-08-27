import React from 'react';
import { cleanup, render } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import GlobalWebChat from '..';

interface AuthState {
  token: string | null;
  isAuthenticated: boolean;
  isCheckingAuth: boolean;
}

interface ClientState {
  clientData: Array<{ name: string }>;
  loading: boolean;
}

interface UserInfoState {
  userId: string;
  selectedGroup: { id: number } | null;
  isSuperUser: boolean;
  loading: boolean;
}

let authState: AuthState = {
  token: null,
  isAuthenticated: false,
  isCheckingAuth: false,
};
let clientState: ClientState = {
  clientData: [],
  loading: false,
};
let userInfoState: UserInfoState = {
  userId: 'alice',
  selectedGroup: { id: 7 },
  isSuperUser: true,
  loading: false,
};
let pathname = '/cmdb';

vi.mock('next/navigation', () => ({
  usePathname: () => pathname,
}));

vi.mock('@/context/auth', () => ({
  useAuth: () => authState,
}));

vi.mock('@/context/client', () => ({
  useClientData: () => ({
    ...clientState,
    appConfigList: [],
    appConfigLoading: false,
  }),
}));

vi.mock('@/context/userInfo', () => ({
  useUserInfoContext: () => userInfoState,
}));

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

const { showError } = vi.hoisted(() => ({ showError: vi.fn() }));

vi.mock('antd', () => ({
  message: {
    error: (content: string) => showError(content),
  },
}));

afterEach(() => {
  cleanup();
  document.querySelectorAll('[data-bk-global-webchat]').forEach((node) => node.remove());
  document.getElementById('webchat-root')?.remove();
  delete window.WebChat;
  authState = {
    token: null,
    isAuthenticated: false,
    isCheckingAuth: false,
  };
  clientState = {
    clientData: [],
    loading: false,
  };
  userInfoState = {
    userId: 'alice',
    selectedGroup: { id: 7 },
    isSuperUser: true,
    loading: false,
  };
  pathname = '/cmdb';
  vi.clearAllMocks();
});

describe('GlobalWebChat', () => {
  it('does not load WebChat before login or without OpsPilot access', () => {
    const { rerender } = render(<GlobalWebChat />);

    expect(document.querySelector('script[data-bk-global-webchat]')).toBeNull();

    authState = {
      token: 'user-token',
      isAuthenticated: true,
      isCheckingAuth: false,
    };
    rerender(<GlobalWebChat />);

    expect(document.querySelector('script[data-bk-global-webchat]')).toBeNull();
  });

  it('loads public assets once and initializes platform mode', () => {
    authState = {
      token: 'user-token',
      isAuthenticated: true,
      isCheckingAuth: false,
    };
    clientState = {
      clientData: [{ name: 'opspilot' }],
      loading: false,
    };

    const initialize = vi.fn(() => {
      const root = document.createElement('div');
      root.id = 'webchat-root';
      document.body.appendChild(root);
    });

    const { rerender } = render(<GlobalWebChat />);
    const script = document.querySelector<HTMLScriptElement>(
      'script[data-bk-global-webchat]',
    );

    expect(script?.getAttribute('src')).toBe('/webchat/webchat.js?v=20260827-5');
    expect(
      document.querySelector<HTMLLinkElement>('link[data-bk-global-webchat]')?.getAttribute('href'),
    ).toBe('/webchat/style.css?v=20260827-5');

    window.WebChat = {
      default: initialize,
    };
    document.querySelector<HTMLLinkElement>('link[data-bk-global-webchat]')
      ?.dispatchEvent(new Event('load'));
    script?.dispatchEvent(new Event('load'));

    expect(initialize).toHaveBeenCalledOnce();
    expect(initialize).toHaveBeenCalledWith(
      expect.objectContaining({
        apiKey: 'user-token',
        userId: 'alice',
        teamId: '7',
        canManageAgents: true,
        manageAgentsUrl: '/opspilot/studio',
        platform: expect.objectContaining({
          applicationsUrl: '/api/proxy/opspilot/skill_channel/platform/',
          deleteSessionUrl: '/api/proxy/opspilot/skill_channel/conversations/delete/',
          storageKey: 'webchat:platform:alice:7',
        }),
        collectContext: expect.any(Function),
      }),
      null,
    );

    rerender(<GlobalWebChat />);
    expect(initialize).toHaveBeenCalledOnce();
  });

  it('removes the floating entry when authorization disappears', () => {
    authState = {
      token: 'user-token',
      isAuthenticated: true,
      isCheckingAuth: false,
    };
    clientState = {
      clientData: [{ name: 'opspilot' }],
      loading: false,
    };
    const initialize = vi.fn(() => {
      const root = document.createElement('div');
      root.id = 'webchat-root';
      document.body.appendChild(root);
    });
    const destroy = vi.fn(() => document.getElementById('webchat-root')?.remove());
    window.WebChat = {
      destroy,
      default: initialize,
    };

    const { rerender } = render(<GlobalWebChat />);
    document.querySelector<HTMLLinkElement>('link[data-bk-global-webchat]')
      ?.dispatchEvent(new Event('load'));
    expect(document.getElementById('webchat-root')).not.toBeNull();

    authState = {
      token: null,
      isAuthenticated: false,
      isCheckingAuth: false,
    };
    rerender(<GlobalWebChat />);

    expect(document.getElementById('webchat-root')).toBeNull();
    expect(destroy).toHaveBeenCalled();
  });

  it('stays hidden and reports an error when a required asset fails', () => {
    authState = {
      token: 'user-token',
      isAuthenticated: true,
      isCheckingAuth: false,
    };
    clientState = {
      clientData: [{ name: 'opspilot' }],
      loading: false,
    };

    render(<GlobalWebChat />);
    document.querySelector<HTMLLinkElement>('link[data-bk-global-webchat]')
      ?.dispatchEvent(new Event('error'));

    expect(document.getElementById('webchat-root')).toBeNull();
    expect(showError).toHaveBeenCalledWith('common.loadFailed');
  });

  it('waits for user info so canManageAgents is not the default superuser flag', () => {
    authState = {
      token: 'user-token',
      isAuthenticated: true,
      isCheckingAuth: false,
    };
    clientState = {
      clientData: [{ name: 'opspilot' }],
      loading: false,
    };
    userInfoState = {
      userId: 'alice',
      selectedGroup: { id: 7 },
      isSuperUser: true,
      loading: true,
    };

    render(<GlobalWebChat />);

    expect(document.querySelector('script[data-bk-global-webchat]')).toBeNull();
  });

  it('tells WebChat when the current user cannot manage agents', () => {
    authState = {
      token: 'user-token',
      isAuthenticated: true,
      isCheckingAuth: false,
    };
    clientState = {
      clientData: [{ name: 'opspilot' }],
      loading: false,
    };
    userInfoState = {
      userId: 'alice',
      selectedGroup: { id: 7 },
      isSuperUser: false,
      loading: false,
    };
    const initialize = vi.fn(() => {
      const root = document.createElement('div');
      root.id = 'webchat-root';
      document.body.appendChild(root);
    });

    render(<GlobalWebChat />);
    window.WebChat = { default: initialize };
    document.querySelector<HTMLLinkElement>('link[data-bk-global-webchat]')
      ?.dispatchEvent(new Event('load'));
    document.querySelector<HTMLScriptElement>('script[data-bk-global-webchat]')
      ?.dispatchEvent(new Event('load'));

    expect(initialize).toHaveBeenCalledWith(
      expect.objectContaining({
        canManageAgents: false,
        manageAgentsUrl: '/opspilot/studio',
      }),
      null,
    );
  });
});
