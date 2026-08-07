import React from 'react';
import { cleanup, render } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.hoisted(() => {
  process.env.NEXT_PUBLIC_WEBCHAT_ENDPOINT =
    '/api/proxy/opspilot/bot_mgmt/execute_chat_flow/80/embedded_chat-1786007476479/';
});

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

let authState: AuthState = {
  token: null,
  isAuthenticated: false,
  isCheckingAuth: false,
};
let clientState: ClientState = {
  clientData: [],
  loading: false,
};

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

  it('loads once and initializes the configured Chatflow for an authorized user', () => {
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

    expect(script?.getAttribute('src')).toBe('/webchat/webchat.js');
    expect(
      document.querySelector<HTMLLinkElement>('link[data-bk-global-webchat]')?.getAttribute('href'),
    ).toBe('/webchat/style.css');

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
        sseUrl: '/api/proxy/opspilot/bot_mgmt/execute_chat_flow/80/embedded_chat-1786007476479/',
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
});
