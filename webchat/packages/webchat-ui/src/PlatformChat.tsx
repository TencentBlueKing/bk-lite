'use client';

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  PlatformAccessDeniedError,
  createPlatformSessionId,
  dockCollapsedStorageKey,
  fillUrlTemplate,
  formatSessionTime,
  isPlatformMode,
  lastSessionStorageKey,
  readDockCollapsed,
  readLastSelection,
  resolvePlatformSelection,
  writeDockCollapsed,
  writeLastSelection,
  type Message,
  type PlatformApplication,
  type PlatformContract,
  type PlatformSession,
} from '@webchat/core';
import type { ChatProps } from './chatProps';
import { WC } from './chrome';
import { ConversationSkeleton } from './components/ConversationSkeleton';
import { PillComposer } from './components/PillComposer';
import {
  fetchPlatformApplications,
  fetchPlatformMessages,
  fetchPlatformSessions,
  interruptPlatformChat,
} from './platform/api';

const Chat = React.lazy(async () => {
  const mod = await import('./Chat');
  return { default: mod.Chat };
});

type DockView = 'sessions' | 'chat';

export interface PlatformChatProps extends ChatProps {
  platform: PlatformContract;
  userId?: string;
  teamId?: string;
  onAccessDenied?: () => void;
}

const QuietIcon: React.FC<{
  title: string;
  onClick: () => void;
  active?: boolean;
  onAccent?: boolean;
  children: React.ReactNode;
}> = React.memo(({ title, onClick, active, onAccent, children }) => (
  <button
    type="button"
    title={title}
    onClick={onClick}
    onMouseDown={(event) => event.stopPropagation()}
    className="flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-md border-none"
    style={{
      color: onAccent ? WC.onPrimary : active ? WC.indigo : WC.muted,
      background: active ? (onAccent ? WC.onPrimaryHover : WC.primaryBg) : 'transparent',
    }}
  >
    {children}
  </button>
));
QuietIcon.displayName = 'QuietIcon';

const FabChatIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
    <path d="M12 3a9 9 0 0 0-7.8 13.5L3 21l4.7-1.1A9 9 0 1 0 12 3zm-3.2 8.2a1.1 1.1 0 1 1 0-2.2 1.1 1.1 0 0 1 0 2.2zm3.2 0a1.1 1.1 0 1 1 0-2.2 1.1 1.1 0 0 1 0 2.2zm3.2 0a1.1 1.1 0 1 1 0-2.2 1.1 1.1 0 0 1 0 2.2z" />
  </svg>
);

export const PlatformChat = React.memo(React.forwardRef<HTMLDivElement, PlatformChatProps>((props, ref) => {
  const {
    platform,
    userId = 'anonymous',
    teamId = 'default',
    onAccessDenied,
    apiKey,
    credentials,
    requestHeaders,
    onClose,
    onStreamingStop,
    ...chatProps
  } = props;

  const requestInit = useMemo(
    () => ({
      apiKey,
      credentials: credentials ?? platform.credentials ?? 'include',
      headers: { ...(platform.headers || {}), ...(requestHeaders || {}) },
    }),
    [apiKey, credentials, platform.credentials, platform.headers, requestHeaders]
  );

  const storagePrefix = platform.storageKey || 'webchat:platform';
  const storageKey = lastSessionStorageKey(storagePrefix, userId, teamId);
  const collapsedKey = dockCollapsedStorageKey(storagePrefix, userId, teamId);
  const storage = typeof window === 'undefined' ? null : window.localStorage;

  const [apps, setApps] = useState<PlatformApplication[]>([]);
  const [sessions, setSessions] = useState<PlatformSession[]>([]);
  const [currentApp, setCurrentApp] = useState<PlatformApplication | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [messagesLoading, setMessagesLoading] = useState(true);
  const [loading, setLoading] = useState(true);
  const [forbidden, setForbidden] = useState(false);
  const [appMenuOpen, setAppMenuOpen] = useState(false);
  const [view, setView] = useState<DockView>('chat');
  const [collapsed, setCollapsed] = useState(() => readDockCollapsed(storage, collapsedKey));
  const [draft, setDraft] = useState('');
  const [kickoffMessage, setKickoffMessage] = useState<string | undefined>();
  const menuRef = useRef<HTMLDivElement>(null);
  const onAccessDeniedRef = useRef(onAccessDenied);
  onAccessDeniedRef.current = onAccessDenied;

  const persistSelection = useCallback(
    (appId: string, nextSessionId: string) => {
      writeLastSelection(storage, storageKey, { appId, sessionId: nextSessionId });
    },
    [storage, storageKey]
  );

  const persistCollapsed = useCallback(
    (next: boolean) => {
      setCollapsed(next);
      writeDockCollapsed(storage, collapsedKey, next);
    },
    [collapsedKey, storage]
  );

  useEffect(() => {
    let cancelled = false;
    async function loadApps() {
      setLoading(true);
      try {
        const nextApps = await fetchPlatformApplications(platform, requestInit);
        if (cancelled) return;
        setApps(nextApps);
        const stored = readLastSelection(storage, storageKey);
        const resolved = resolvePlatformSelection(nextApps, [], stored);
        setCurrentApp((prev) => (prev?.id === resolved.app?.id ? prev : resolved.app));
      } catch (error) {
        if (cancelled) return;
        if (error instanceof PlatformAccessDeniedError) {
          setForbidden(true);
          onAccessDeniedRef.current?.();
        } else {
          setApps([]);
          setCurrentApp(null);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    void loadApps();
    return () => {
      cancelled = true;
    };
  }, [platform, requestInit, storage, storageKey]);

  const currentAppId = currentApp?.id;
  const currentChannelId = currentApp?.channelId;

  useEffect(() => {
    let cancelled = false;
    async function loadSessions() {
      if (!currentAppId || !currentChannelId) {
        setSessions([]);
        setSessionId(null);
        setMessages([]);
        return;
      }
      try {
        const nextSessions = await fetchPlatformSessions(
          platform,
          { channelId: currentChannelId },
          requestInit
        );
        if (cancelled) return;
        setSessions(nextSessions);
        const stored = readLastSelection(storage, storageKey);
        const resolved = resolvePlatformSelection(
          [{ id: currentAppId, name: '', channelId: currentChannelId }],
          nextSessions,
          stored
        );
        setSessionId((current) => {
          const nextId = resolved.sessionId || current || createPlatformSessionId();
          persistSelection(currentAppId, nextId);
          return nextId;
        });
      } catch {
        if (cancelled) return;
        const nextSessionId = createPlatformSessionId();
        setSessions([]);
        setSessionId(nextSessionId);
      }
    }
    void loadSessions();
    return () => {
      cancelled = true;
    };
  }, [currentAppId, currentChannelId, persistSelection, platform, requestInit, storage, storageKey]);

  const isDraftSession =
    !!sessionId &&
    sessionId.startsWith('session_') &&
    !sessions.some((item) => item.id === sessionId);

  useEffect(() => {
    let cancelled = false;
    async function loadMessages() {
      if (!sessionId || isDraftSession) {
        setMessages([]);
        setMessagesLoading(false);
        return;
      }
      setMessagesLoading(true);
      try {
        const nextMessages = await fetchPlatformMessages(platform, sessionId, requestInit);
        if (!cancelled) {
          setMessages(nextMessages);
        }
      } catch {
        if (!cancelled) {
          setMessages([]);
        }
      } finally {
        if (!cancelled) {
          setMessagesLoading(false);
        }
      }
    }
    void loadMessages();
    return () => {
      cancelled = true;
    };
  }, [isDraftSession, platform, requestInit, sessionId]);

  useEffect(() => {
    const onPointerDown = (event: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setAppMenuOpen(false);
      }
    };
    document.addEventListener('mousedown', onPointerDown);
    return () => document.removeEventListener('mousedown', onPointerDown);
  }, []);

  const chatUrl = currentApp
    ? fillUrlTemplate(platform.chatUrlTemplate, {
        channelId: currentApp.channelId,
      })
    : undefined;

  const handleNewChat = useCallback(() => {
    if (!currentAppId) return;
    const nextSessionId = createPlatformSessionId();
    setSessionId(nextSessionId);
    setMessages([]);
    setMessagesLoading(false);
    setView('chat');
    persistSelection(currentAppId, nextSessionId);
  }, [currentAppId, persistSelection]);

  const handleSelectApp = useCallback((app: PlatformApplication) => {
    setCurrentApp(app);
    setAppMenuOpen(false);
    setMessages([]);
    setMessagesLoading(true);
    setView('chat');
  }, []);

  const handleSelectSession = useCallback((id: string) => {
    setSessionId(id);
    setMessages([]);
    setMessagesLoading(true);
    setView('chat');
    if (currentAppId) persistSelection(currentAppId, id);
  }, [currentAppId, persistSelection]);

  const handleStreamingStop = useCallback(() => {
    void interruptPlatformChat(platform, requestInit);
    onStreamingStop?.();
  }, [onStreamingStop, platform, requestInit]);

  const handleClose = useCallback(() => {
    persistCollapsed(true);
    onClose?.();
  }, [onClose, persistCollapsed]);

  const handleComposerSend = useCallback(() => {
    const text = draft.trim();
    if (!text || !currentAppId) return;
    if (!isDraftSession) {
      const nextSessionId = createPlatformSessionId();
      setSessionId(nextSessionId);
      setMessages([]);
      setMessagesLoading(false);
      persistSelection(currentAppId, nextSessionId);
    }
    setView('chat');
    setKickoffMessage(text);
    setDraft('');
  }, [currentAppId, draft, isDraftSession, persistSelection]);

  const sessionCustomData = useMemo(
    () => (sessionId ? { session_id: sessionId } : undefined),
    [sessionId]
  );

  if (forbidden) {
    return null;
  }

  const emptyApps = !loading && apps.length === 0;

  if (collapsed) {
    return (
      <div ref={ref} className="fixed bottom-5 right-2 z-50">
        <button
          type="button"
          title="打开对话"
          aria-label="打开对话"
          onClick={() => persistCollapsed(false)}
          className="flex h-10 w-10 items-center justify-center rounded-full border-none"
          style={{ background: WC.indigo, color: WC.onPrimary }}
        >
          <FabChatIcon />
        </button>
      </div>
    );
  }

  const headerTitle = emptyApps ? '会话' : currentApp?.name || '平台助手';
  const listItems: PlatformSession[] =
    isDraftSession && sessionId ? [{ id: sessionId, title: '新会话' }, ...sessions] : sessions;

  return (
    <div
      ref={ref}
      className="fixed inset-y-0 right-0 z-[1100] flex w-[380px] flex-col overflow-hidden font-sans"
      style={{ background: WC.white, borderLeft: `1px solid ${WC.botBorder}` }}
    >
      <div ref={menuRef} className="relative flex-shrink-0">
        <div
          className="flex h-[52px] items-center gap-2 pl-4 pr-2"
          style={{ background: WC.indigo, color: WC.onPrimary }}
        >
          {emptyApps ? (
            <div className="min-w-0 flex-1 truncate text-sm font-semibold">会话</div>
          ) : (
            <button
              type="button"
              title="切换智能体"
              onClick={() => setAppMenuOpen((open) => !open)}
              className="flex min-w-0 flex-1 items-center gap-1 border-none bg-transparent p-0 text-left text-sm font-semibold"
              style={{ color: WC.onPrimary }}
            >
              <span className="truncate">{headerTitle}</span>
              <svg
                width="14"
                height="14"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                className="flex-shrink-0"
              >
                <path d={appMenuOpen ? 'M18 15l-6-6-6 6' : 'M6 9l6 6 6-6'} />
              </svg>
            </button>
          )}
          {!emptyApps && (
            <>
              <QuietIcon title="新对话" onClick={handleNewChat} onAccent>
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M12 5v14M5 12h14" />
                </svg>
              </QuietIcon>
              <QuietIcon title="会话" onClick={() => setView('sessions')} active={view === 'sessions'} onAccent>
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M3 12a9 9 0 1 0 3-6.7" />
                  <path d="M3 4v5h5" />
                  <path d="M12 7v5l3 2" />
                </svg>
              </QuietIcon>
            </>
          )}
          <QuietIcon title="关闭" onClick={handleClose} onAccent>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <rect x="3" y="4" width="18" height="16" rx="2" />
              <path d="M15 4v16" />
            </svg>
          </QuietIcon>
        </div>
        {appMenuOpen && !emptyApps ? (
          <div
            className="absolute left-2 right-2 top-[52px] z-20 overflow-hidden rounded-lg"
            style={{ background: WC.white, border: `1px solid ${WC.botBorder}` }}
          >
            {apps.map((app) => {
              const active = app.id === currentApp?.id;
              return (
                <button
                  key={app.id}
                  type="button"
                  className="block w-full truncate px-3 py-2 text-left text-[13px]"
                  style={{
                    background: active ? WC.primaryBg : WC.white,
                    color: active ? WC.indigo : WC.botText,
                    fontWeight: active ? 600 : 400,
                    borderBottom: `1px solid ${WC.botBorder}`,
                  }}
                  onClick={() => handleSelectApp(app)}
                >
                  {app.name}
                </button>
              );
            })}
          </div>
        ) : null}
      </div>

      {emptyApps ? (
        <div
          className="flex flex-1 flex-col items-center justify-center px-7 text-center"
          style={{ background: WC.page, color: WC.muted }}
        >
          <p className="text-sm font-medium" style={{ color: WC.botText }}>
            当前团队还没有可对话的智能体
          </p>
          <p className="mt-2 text-xs leading-[18px]">
            需要在智能体详情开通并启用「平台」渠道，且当前组织在使用组织内。
          </p>
        </div>
      ) : view === 'sessions' ? (
        <>
          <div className="min-h-0 flex-1 overflow-y-auto px-2 py-1.5">
            {loading ? (
              <div className="p-3">
                <ConversationSkeleton />
              </div>
            ) : listItems.length === 0 ? (
              <p className="px-2.5 py-3 text-xs" style={{ color: WC.muted }}>
                暂无会话
              </p>
            ) : (
              listItems.map((session) => {
                const active = session.id === sessionId;
                const time = formatSessionTime(session.updatedAt);
                return (
                  <button
                    key={session.id}
                    type="button"
                    onClick={() => handleSelectSession(session.id)}
                    className="mb-0.5 block w-full rounded-lg px-2.5 py-2.5 text-left"
                    style={{
                      background: active ? WC.primaryBg : 'transparent',
                      color: WC.botText,
                    }}
                  >
                    <div className="truncate text-[13px] font-normal leading-[18px]">{session.title}</div>
                    <div className="mt-1 flex justify-end text-[10px] leading-4" style={{ color: WC.dim }}>
                      {time || ''}
                    </div>
                  </button>
                );
              })
            )}
            {listItems.length > 0 && (
              <div className="px-2.5 py-2.5 text-xs" style={{ color: WC.indigo }}>
                共 {listItems.length} 条
              </div>
            )}
          </div>
          <div className="relative flex-shrink-0 p-2.5">
            <PillComposer
              value={draft}
              onChange={setDraft}
              onSubmit={() => handleComposerSend()}
              placeholder="请输入消息..."
            />
          </div>
        </>
      ) : (
        <div className="flex min-h-0 flex-1 flex-col">
          {currentApp && sessionId && chatUrl ? (
            <React.Suspense
              fallback={
                <div className="flex-1 p-4">
                  <ConversationSkeleton />
                </div>
              }
            >
              <Chat
                key={currentApp.id}
                {...chatProps}
                sseUrl={chatUrl}
                showHeader={false}
                enableStorage={false}
                apiKey={apiKey}
                credentials={requestInit.credentials}
                requestHeaders={requestInit.headers}
                platform={platform}
                historyLoading={messagesLoading}
                initialMessages={messages}
                customData={sessionCustomData}
                kickoffMessage={kickoffMessage}
                onKickoffConsumed={() => setKickoffMessage(undefined)}
                onClose={handleClose}
                onStreamingStop={handleStreamingStop}
                placeholder="请输入消息..."
              />
            </React.Suspense>
          ) : (
            <div className="flex-1 p-4">
              <ConversationSkeleton />
            </div>
          )}
        </div>
      )}
    </div>
  );
}));

PlatformChat.displayName = 'PlatformChat';

export function shouldRenderPlatformChat(props: Pick<PlatformChatProps, 'platform' | 'sseUrl'>): boolean {
  return isPlatformMode(props);
}
