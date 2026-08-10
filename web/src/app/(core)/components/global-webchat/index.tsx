'use client';

import { useEffect, useMemo } from 'react';
import { message } from 'antd';

import { useAuth } from '@/context/auth';
import { useClientData } from '@/context/client';
import { useTranslation } from '@/utils/i18n';

import './global-webchat.css';

const WEBCHAT_SCRIPT_URL = '/webchat/webchat.js';
const WEBCHAT_STYLE_URL = '/webchat/style.css';
const WEBCHAT_ROOT_ID = 'webchat-root';
const WEBCHAT_ENDPOINT = process.env.NEXT_PUBLIC_WEBCHAT_ENDPOINT;

interface WebChatInitConfig {
  apiKey: string;
  customData: Record<string, unknown>;
  position: 'bottom-right';
  sseUrl: string;
}

interface WebChatBrowserApi {
  default: (config: WebChatInitConfig, elementId: string | null) => void;
  destroy?: () => void;
}

declare global {
  interface Window {
    WebChat?: WebChatBrowserApi;
  }
}

const ensureStylesheet = () => {
  const existing = document.querySelector<HTMLLinkElement>(
    'link[data-bk-global-webchat="style"]',
  );
  if (existing) {
    return existing;
  }

  const stylesheet = document.createElement('link');
  stylesheet.rel = 'stylesheet';
  stylesheet.href = WEBCHAT_STYLE_URL;
  stylesheet.dataset.bkGlobalWebchat = 'style';
  document.head.appendChild(stylesheet);
  return stylesheet;
};

const getOrCreateScript = () => {
  const existing = document.querySelector<HTMLScriptElement>(
    'script[data-bk-global-webchat="script"]',
  );
  if (existing) {
    return existing;
  }

  const script = document.createElement('script');
  script.src = WEBCHAT_SCRIPT_URL;
  script.async = true;
  script.dataset.bkGlobalWebchat = 'script';
  document.body.appendChild(script);
  return script;
};

const destroyWebChat = () => {
  window.WebChat?.destroy?.();
  document.getElementById(WEBCHAT_ROOT_ID)?.remove();
};

const GlobalWebChat = () => {
  const { token, isAuthenticated, isCheckingAuth } = useAuth();
  const { clientData, loading: clientsLoading } = useClientData();
  const { t } = useTranslation();
  const loadErrorMessage = t('common.loadFailed');
  const hasOpsPilotAccess = useMemo(
    () => clientData.some((client) => client.name === 'opspilot'),
    [clientData],
  );
  const canLoad = Boolean(
    isAuthenticated
      && token
      && !isCheckingAuth
      && !clientsLoading
      && hasOpsPilotAccess,
  );

  useEffect(() => {
    if (!canLoad || !token || !WEBCHAT_ENDPOINT) {
      destroyWebChat();
      return undefined;
    }

    let active = true;
    let hasFailed = false;
    const stylesheet = ensureStylesheet();
    const script = getOrCreateScript();
    let stylesheetReady = stylesheet.dataset.loadState === 'loaded' || Boolean(stylesheet.sheet);
    let scriptReady = Boolean(window.WebChat);

    const initialize = () => {
      if (
        !active
        || hasFailed
        || !stylesheetReady
        || !scriptReady
        || document.getElementById(WEBCHAT_ROOT_ID)
        || !window.WebChat
      ) {
        return;
      }

      window.WebChat.default(
        {
          apiKey: token,
          customData: { type: 'agui' },
          position: 'bottom-right',
          sseUrl: WEBCHAT_ENDPOINT,
        },
        null,
      );
    };

    const handleStylesheetLoad = () => {
      stylesheet.dataset.loadState = 'loaded';
      stylesheetReady = true;
      initialize();
    };
    const handleScriptLoad = () => {
      script.dataset.loadState = 'loaded';
      scriptReady = true;
      initialize();
    };
    const handleResourceError = (event: Event) => {
      const resource = event.currentTarget;
      if (resource instanceof HTMLElement) {
        resource.remove();
      }
      if (active && !hasFailed) {
        hasFailed = true;
        destroyWebChat();
        message.error(loadErrorMessage);
      }
    };

    stylesheet.addEventListener('load', handleStylesheetLoad);
    stylesheet.addEventListener('error', handleResourceError);
    script.addEventListener('load', handleScriptLoad);
    script.addEventListener('error', handleResourceError);
    initialize();

    return () => {
      active = false;
      stylesheet.removeEventListener('load', handleStylesheetLoad);
      stylesheet.removeEventListener('error', handleResourceError);
      script.removeEventListener('load', handleScriptLoad);
      script.removeEventListener('error', handleResourceError);
      destroyWebChat();
    };
  }, [canLoad, loadErrorMessage, token]);

  return null;
};

export default GlobalWebChat;
