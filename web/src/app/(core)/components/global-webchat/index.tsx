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
  applicationsUrl: '/api/proxy/opspilot/skill_channel/platform/',
  sessionsUrl: '/api/proxy/opspilot/skill_channel/conversations/?channel_id={channelId}',
  messagesUrl: '/api/proxy/opspilot/skill_channel/conversations/messages/?session_id={sessionId}',
  chatUrlTemplate: '/api/proxy/opspilot/skill_channel/{channelId}/chat/',
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
