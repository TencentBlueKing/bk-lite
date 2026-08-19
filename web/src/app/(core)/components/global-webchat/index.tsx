'use client';

import { useRef } from 'react';
import { usePathname } from 'next/navigation';
import { PlatformChat } from '@webchat/ui';
import { useAuth } from '@/context/auth';
import { useClientData } from '@/context/client';
import { useUserInfoContext } from '@/context/userInfo';
import {
  hasOpsPilotClientAccess,
  lastWebchatStorageKey,
  shouldKeepGlobalWebchat,
} from './visibility';

const PLATFORM = {
  applicationsUrl: '/api/proxy/opspilot/bot_mgmt/chat_application/?app_type=web_chat&page_size=100',
  sessionsUrl: '/api/proxy/opspilot/bot_mgmt/chat_application/web_chat_sessions/?bot_id={botId}&node_id={nodeId}',
  messagesUrl: '/api/proxy/opspilot/bot_mgmt/chat_application/session_messages/?session_id={sessionId}',
  chatUrlTemplate: '/api/proxy/opspilot/bot_mgmt/execute_chat_flow/{botId}/{nodeId}/',
  interruptUrl: '/api/proxy/opspilot/bot_mgmt/interrupt_chat_flow_execution/',
  approvalUrl: '/api/proxy/opspilot/bot_mgmt/submit_approval/',
  choiceUrl: '/api/proxy/opspilot/bot_mgmt/submit_choice/',
  credentials: 'include' as const,
  storageKey: 'webchat:platform',
};

const GlobalWebchat = () => {
  const pathname = usePathname();
  const { isAuthenticated, token } = useAuth();
  const { clientData, appConfigList, loading, appConfigLoading } = useClientData();
  const { userId, selectedGroup } = useUserInfoContext();
  const apps = appConfigList.length > 0 ? appConfigList : clientData;
  const mountedRef = useRef(false);

  const shouldMount = shouldKeepGlobalWebchat({
    authenticated: isAuthenticated,
    clientLoading: loading || appConfigLoading,
    hasOpsPilotAccess: hasOpsPilotClientAccess(apps),
    pathname,
    alreadyMounted: mountedRef.current,
  });
  mountedRef.current = shouldMount;

  if (!shouldMount) {
    return null;
  }

  const teamId = String(selectedGroup?.id || 'default');

  return (
    <PlatformChat
      key={lastWebchatStorageKey(userId || 'anonymous', teamId)}
      platform={PLATFORM}
      apiKey={token || undefined}
      credentials="include"
      userId={userId || 'anonymous'}
      teamId={teamId}
      placeholder="请输入消息..."
    />
  );
};

export default GlobalWebchat;
