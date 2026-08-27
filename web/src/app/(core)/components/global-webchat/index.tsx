'use client';

import { useEffect, useRef } from 'react';
import { usePathname } from 'next/navigation';
import { message } from 'antd';

import { installPageContextBridge } from '@/components/ai-page-context/registry';
import { useAuth } from '@/context/auth';
import { useClientData } from '@/context/client';
import { useUserInfoContext } from '@/context/userInfo';
import { useTranslation } from '@/utils/i18n';

import {
  hasOpsPilotClientAccess,
  lastWebchatStorageKey,
  shouldKeepGlobalWebchat,
} from './visibility';
import './global-webchat.css';

const WEBCHAT_SCRIPT_URL = '/webchat/webchat.js?v=20260827-3';
const WEBCHAT_STYLE_URL = '/webchat/style.css?v=20260827-3';
const WEBCHAT_ROOT_ID = 'webchat-root';
const MANAGE_AGENTS_URL = '/opspilot/studio';

const PLATFORM = {
  applicationsUrl: '/api/proxy/opspilot/skill_channel/platform/',
  sessionsUrl: '/api/proxy/opspilot/skill_channel/conversations/?channel_id={channelId}',
  messagesUrl: '/api/proxy/opspilot/skill_channel/conversations/messages/?session_id={sessionId}',
  deleteSessionUrl: '/api/proxy/opspilot/skill_channel/conversations/delete/',
  chatUrlTemplate: '/api/proxy/opspilot/skill_channel/{channelId}/chat/',
  interruptUrl: '/api/proxy/opspilot/bot_mgmt/interrupt_chat_flow_execution/',
  approvalUrl: '/api/proxy/opspilot/bot_mgmt/submit_approval/',
  choiceUrl: '/api/proxy/opspilot/bot_mgmt/submit_choice/',
  credentials: 'include' as const,
};

interface WebChatPlatformConfig {
  apiKey?: string;
  credentials?: RequestCredentials;
  placeholder?: string;
  position: 'bottom-right';
  platform: typeof PLATFORM & { storageKey: string };
  userId: string;
  teamId: string;
  canManageAgents?: boolean;
  manageAgentsUrl?: string;
  collectContext?: (hint?: { message?: string }) => Promise<unknown>;
}

interface WebChatBrowserApi {
  default: (config: WebChatPlatformConfig, elementId: string | null) => void;
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
  document.documentElement.style.setProperty('--bk-webchat-dock-width', '0px');
};

const GlobalWebchat = () => {
  const pathname = usePathname();
  const { token, isAuthenticated, isCheckingAuth } = useAuth();
  const { clientData, appConfigList, loading, appConfigLoading } = useClientData();
  const { userId, selectedGroup, isSuperUser, loading: userInfoLoading } = useUserInfoContext();
  const { t } = useTranslation();
  const loadErrorMessage = t('common.loadFailed');
  const apps = appConfigList.length > 0 ? appConfigList : clientData;
  const mountedRef = useRef(false);

  const shouldMount = shouldKeepGlobalWebchat({
    authenticated: isAuthenticated && !isCheckingAuth,
    clientLoading: loading || appConfigLoading,
    userInfoLoading,
    hasOpsPilotAccess: hasOpsPilotClientAccess(apps),
    pathname,
    alreadyMounted: mountedRef.current,
  });
  mountedRef.current = shouldMount;

  const teamId = String(selectedGroup?.id || 'default');
  const resolvedUserId = userId || 'anonymous';
  const storageKey = lastWebchatStorageKey(resolvedUserId, teamId);

  useEffect(() => {
    if (!shouldMount || !token) {
      destroyWebChat();
      return undefined;
    }

    let active = true;
    let hasFailed = false;
    const stylesheet = ensureStylesheet();
    const script = getOrCreateScript();
    let stylesheetReady =
      stylesheet.dataset.loadState === 'loaded' || Boolean(stylesheet.sheet);
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
          credentials: 'include',
          placeholder: '请输入消息...',
          position: 'bottom-right',
          platform: {
            ...PLATFORM,
            storageKey,
          },
          userId: resolvedUserId,
          teamId,
          canManageAgents: isSuperUser,
          manageAgentsUrl: MANAGE_AGENTS_URL,
          collectContext: async (hint) => {
            installPageContextBridge();
            return window.__BK_AI_PAGE_CONTEXT__?.collect(hint) ?? null;
          },
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
  }, [shouldMount, token, storageKey, resolvedUserId, teamId, isSuperUser, loadErrorMessage]);

  return null;
};

export default GlobalWebchat;
