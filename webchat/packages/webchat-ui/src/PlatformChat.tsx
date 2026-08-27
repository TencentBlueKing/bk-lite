'use client';

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import {
  PlatformAccessDeniedError,
  createPlatformSessionId,
  fillUrlTemplate,
  formatSessionTime,
  isPersistedPlatformSession,
  isPlatformMode,
  lastSessionStorageKey,
  PLATFORM_DOCK_CHAT_WIDTH,
  PLATFORM_HISTORY_RAIL_DOCK,
  platformDockInsetWidth,
  readLastSelection,
  removePlatformSession,
  resolvePlatformSelection,
  sessionTitleFromUserContent,
  shouldFetchPlatformMessages,
  shouldRefreshPlatformSessions,
  shouldShowPlatformLauncher,
  WEBCHAT_DOCK_INSET_VAR,
  writeLastSelection,
  type Message,
  type PlatformApplication,
  type PlatformContract,
  type PlatformSession,
  type ChatState,
} from '@webchat/core';
import type { ChatProps } from './chatProps';
import { WC } from './chrome';
import { ConversationSkeleton } from './components/ConversationSkeleton';
import {
  deletePlatformSession,
  fetchPlatformApplications,
  fetchPlatformMessages,
  fetchPlatformSessions,
  interruptPlatformChat,
} from './platform/api';

const Chat = React.lazy(async () => {
  const mod = await import('./Chat');
  return { default: mod.Chat };
});

const HISTORY_RAIL_FULL = 240;

export interface PlatformChatProps extends ChatProps {
  platform: PlatformContract;
  userId?: string;
  teamId?: string;
  onAccessDenied?: () => void;
  /** Super-admin (or equivalent) may see an empty-state guide. Non-managers hide the FAB. */
  canManageAgents?: boolean;
  /** Host console path for publishing agents. WebChat does not hardcode this. */
  manageAgentsUrl?: string;
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
    aria-label={title}
    aria-pressed={active}
    onClick={onClick}
    onMouseDown={(event) => event.stopPropagation()}
    className="flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-md border-none hover:bg-[var(--color-fill-2,#f4f5f8)]"
    style={{
      color: onAccent ? WC.onPrimary : active ? WC.indigo : WC.muted,
      background: active
        ? onAccent
          ? WC.onPrimaryHover
          : WC.primaryBg
        : 'transparent',
    }}
  >
    {children}
  </button>
));
QuietIcon.displayName = 'QuietIcon';

const HistoryRail: React.FC<{
  items: PlatformSession[];
  sessionId: string | null;
  loading: boolean;
  wide: boolean;
  onSelect: (id: string) => void;
  canDelete: (id: string) => boolean;
  confirmingDeleteId: string | null;
  deletingId: string | null;
  onRequestDelete: (id: string) => void;
  onConfirmDelete: (id: string) => void;
  onCancelDelete: () => void;
}> = React.memo(({
  items,
  sessionId,
  loading,
  wide,
  onSelect,
  canDelete,
  confirmingDeleteId,
  deletingId,
  onRequestDelete,
  onConfirmDelete,
  onCancelDelete,
}) => {
  const [tip, setTip] = useState<{ text: string; top: number; left: number } | null>(null);

  const hideTip = useCallback(() => setTip(null), []);

  const showTip = useCallback((event: React.SyntheticEvent<HTMLButtonElement>, text: string) => {
    const titleEl = event.currentTarget.querySelector('[data-session-title]');
    if (!(titleEl instanceof HTMLElement) || titleEl.scrollWidth <= titleEl.clientWidth) {
      setTip(null);
      return;
    }
    const rect = event.currentTarget.getBoundingClientRect();
    setTip({
      text,
      top: rect.top + rect.height / 2,
      left: rect.right + 8,
    });
  }, []);

  return (
    <aside
      className="flex h-full min-h-0 flex-shrink-0 flex-col"
      style={{
        width: wide ? HISTORY_RAIL_FULL : PLATFORM_HISTORY_RAIL_DOCK,
        background: WC.historyRail,
        borderRight: `1px solid ${WC.botBorder}`,
      }}
      aria-label="历史会话"
    >
      <div className="flex-shrink-0 px-3 py-2.5 text-xs" style={{ color: WC.muted }}>
        历史对话
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto px-1.5 pb-2" onScroll={hideTip}>
        {loading ? (
          <p className="px-2 py-2 text-xs" style={{ color: WC.muted }}>
            加载中…
          </p>
        ) : items.length === 0 ? (
          <p className="px-2 py-2 text-xs" style={{ color: WC.muted }}>
            暂无会话
          </p>
        ) : (
          items.map((session) => {
            const active = session.id === sessionId;
            const time = formatSessionTime(session.updatedAt);
            const confirming = confirmingDeleteId === session.id;
            const deleting = deletingId === session.id;
            return (
              <div
                key={session.id}
                className="group mb-0.5 flex items-start gap-1 rounded-md px-2 py-2"
                style={{
                  background: active ? WC.primaryBg : 'transparent',
                  color: active ? WC.indigo : WC.botText,
                }}
              >
                <button
                  type="button"
                  aria-label={session.title}
                  onClick={() => onSelect(session.id)}
                  onMouseEnter={(event) => showTip(event, session.title)}
                  onMouseLeave={hideTip}
                  onFocus={(event) => showTip(event, session.title)}
                  onBlur={hideTip}
                  className="min-w-0 flex-1 border-none bg-transparent p-0 text-left"
                  style={{ color: active ? WC.indigo : WC.botText }}
                >
                  <div data-session-title className="truncate text-[13px] leading-[18px]">
                    {session.title}
                  </div>
                  {time ? (
                    <div className="mt-1 text-[10px] leading-4" style={{ color: WC.dim }}>
                      {time}
                    </div>
                  ) : null}
                </button>
                {canDelete(session.id) ? (
                  confirming ? (
                    <div className="flex flex-shrink-0 items-center gap-1 pt-0.5">
                      <button
                        type="button"
                        disabled={deleting}
                        onClick={() => onConfirmDelete(session.id)}
                        className="border-none bg-transparent p-0 text-[11px]"
                        style={{ color: WC.fail }}
                      >
                        {deleting ? '删除中' : '删除'}
                      </button>
                      <button
                        type="button"
                        disabled={deleting}
                        onClick={onCancelDelete}
                        className="border-none bg-transparent p-0 text-[11px]"
                        style={{ color: WC.muted }}
                      >
                        取消
                      </button>
                    </div>
                  ) : (
                    <button
                      type="button"
                      title="删除会话"
                      aria-label="删除会话"
                      onClick={() => onRequestDelete(session.id)}
                      className="mt-0.5 flex h-6 w-6 flex-shrink-0 cursor-pointer items-center justify-center rounded border-none opacity-0 transition-opacity duration-150 group-hover:opacity-100 group-focus-within:opacity-100 focus-visible:opacity-100"
                      style={{ color: WC.dim, background: 'transparent' }}
                    >
                      <svg
                        width="14"
                        height="14"
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth="2"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                      >
                        <path d="M3 6h18" />
                        <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6" />
                        <path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
                        <line x1="10" x2="10" y1="11" y2="17" />
                        <line x1="14" x2="14" y1="11" y2="17" />
                      </svg>
                    </button>
                  )
                ) : null}
              </div>
            );
          })
        )}
      </div>
      {tip
        ? createPortal(
            <div
              role="tooltip"
              className="pointer-events-none fixed z-[2100] max-w-[240px] rounded-md px-2.5 py-1.5 text-[12px] leading-[18px]"
              style={{
                top: tip.top,
                left: tip.left,
                transform: 'translateY(-50%)',
                background: WC.botText,
                color: WC.white,
                boxShadow: WC.shadow,
              }}
            >
              {tip.text}
            </div>,
            document.body
          )
        : null}
    </aside>
  );
});
HistoryRail.displayName = 'HistoryRail';

function webchatAssetUrl(fileName: string): string {
  if (typeof document === 'undefined') {
    return `/webchat/${fileName}`;
  }
  const script = document.querySelector<HTMLScriptElement>(
    'script[data-bk-global-webchat="script"], script[src*="webchat.js"]'
  );
  if (!script?.src) {
    return `/webchat/${fileName}`;
  }
  const url = new URL(fileName, script.src);
  url.search = new URL(script.src).search;
  return url.toString();
}

const FabLauncher: React.FC<{ onOpen: () => void }> = ({ onOpen }) => {
  const webpSrc = webchatAssetUrl('fab-whaledou.webp');
  const pngSrc = webchatAssetUrl('fab-whaledou.png');

  return (
    <button
      type="button"
      title="打开对话"
      aria-label="打开对话"
      onClick={onOpen}
      className="wc-fab-launcher"
    >
      <picture>
        <source srcSet={webpSrc} type="image/webp" media="(prefers-reduced-motion: no-preference)" />
        <img src={pngSrc} alt="" width={72} height={72} draggable={false} />
      </picture>
    </button>
  );
};

export const PlatformChat = React.memo(React.forwardRef<HTMLDivElement, PlatformChatProps>((props, ref) => {
  const {
    platform,
    userId = 'anonymous',
    teamId = 'default',
    onAccessDenied,
    canManageAgents,
    manageAgentsUrl,
    apiKey,
    credentials,
    requestHeaders,
    onClose,
    onStreamingStop,
    onStateChange,
    showFullscreenButton = true,
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
  // Session/app selection stays in localStorage. Dock open/collapsed is
  // in-memory only so new windows and refreshes always start as FAB.
  // After the first open, keep Chat mounted and only toggle visibility on
  // close — unmounting would drop in-memory draft messages.
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
  const [historyOpen, setHistoryOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(true);
  const [hasOpened, setHasOpened] = useState(false);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [confirmingDeleteId, setConfirmingDeleteId] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [draftTitle, setDraftTitle] = useState('新会话');
  const chatStateRef = useRef<ChatState>('idle');
  const menuRef = useRef<HTMLDivElement>(null);
  const loadedSessionIdRef = useRef<string | null>(null);
  const onAccessDeniedRef = useRef(onAccessDenied);
  onAccessDeniedRef.current = onAccessDenied;

  const persistSelection = useCallback(
    (appId: string, nextSessionId: string) => {
      writeLastSelection(storage, storageKey, { appId, sessionId: nextSessionId });
    },
    [storage, storageKey]
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
        const nextId = resolved.sessionId || createPlatformSessionId();
        setSessionId(nextId);
        persistSelection(currentAppId, nextId);
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
      if (!sessionId) {
        loadedSessionIdRef.current = null;
        setMessages([]);
        if (!currentAppId) {
          setMessagesLoading(false);
        }
        return;
      }
      if (
        !shouldFetchPlatformMessages({
          sessionId,
          loadedSessionId: loadedSessionIdRef.current,
          sessions,
        })
      ) {
        loadedSessionIdRef.current = sessionId;
        setMessagesLoading(false);
        return;
      }
      setMessagesLoading(true);
      try {
        const nextMessages = await fetchPlatformMessages(platform, sessionId, requestInit);
        if (!cancelled) {
          loadedSessionIdRef.current = sessionId;
          setMessages(nextMessages);
        }
      } catch {
        if (!cancelled) {
          loadedSessionIdRef.current = sessionId;
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
  }, [currentAppId, platform, requestInit, sessionId, sessions]);

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
    loadedSessionIdRef.current = nextSessionId;
    setDraftTitle('新会话');
    setSessionId(nextSessionId);
    setMessages([]);
    setMessagesLoading(false);
    persistSelection(currentAppId, nextSessionId);
  }, [currentAppId, persistSelection]);

  const handleSelectApp = useCallback((app: PlatformApplication) => {
    setAppMenuOpen(false);
    if (app.id === currentAppId) return;
    setCurrentApp(app);
    setSessions([]);
    loadedSessionIdRef.current = null;
    setDraftTitle('新会话');
    setSessionId(null);
    setMessages([]);
    setMessagesLoading(true);
  }, [currentAppId]);

  const handleSelectSession = useCallback((id: string) => {
    setConfirmingDeleteId(null);
    if (id === sessionId) return;
    loadedSessionIdRef.current = null;
    setDraftTitle('新会话');
    setSessionId(id);
    setMessages([]);
    setMessagesLoading(
      shouldFetchPlatformMessages({
        sessionId: id,
        loadedSessionId: null,
        sessions,
      })
    );
    if (currentAppId) persistSelection(currentAppId, id);
  }, [currentAppId, persistSelection, sessionId, sessions]);

  const handleDeleteSession = useCallback(
    async (id: string) => {
      const persisted = isPersistedPlatformSession(id, sessions);
      if (persisted) {
        if (!platform.deleteSessionUrl) {
          return;
        }
        setDeletingId(id);
        try {
          await deletePlatformSession(platform, id, requestInit);
        } catch {
          setDeletingId(null);
          return;
        }
        setDeletingId(null);
      }
      const next = removePlatformSession(sessions, id, sessionId);
      setSessions(next.sessions);
      setConfirmingDeleteId(null);
      if (next.currentId !== null || !currentAppId) {
        return;
      }
      const nextSessionId = createPlatformSessionId();
      loadedSessionIdRef.current = nextSessionId;
      setDraftTitle('新会话');
      setSessionId(nextSessionId);
      setMessages([]);
      setMessagesLoading(false);
      persistSelection(currentAppId, nextSessionId);
    },
    [currentAppId, persistSelection, platform, requestInit, sessionId, sessions]
  );

  const handleStreamingStop = useCallback(() => {
    void interruptPlatformChat(platform, requestInit);
    onStreamingStop?.();
  }, [onStreamingStop, platform, requestInit]);

  const refreshSessions = useCallback(() => {
    if (!currentChannelId) return;
    void fetchPlatformSessions(platform, { channelId: currentChannelId }, requestInit)
      .then((nextSessions) => {
        setSessions(nextSessions);
      })
      .catch(() => undefined);
  }, [currentChannelId, platform, requestInit]);

  const handleChatStateChange = useCallback(
    (state: ChatState) => {
      const from = chatStateRef.current;
      chatStateRef.current = state;
      if (shouldRefreshPlatformSessions(from, state)) {
        refreshSessions();
      }
      onStateChange?.(state);
    },
    [onStateChange, refreshSessions]
  );

  const handleMessageReceived = useCallback(
    (message: Message) => {
      if (
        message.sender === 'user' &&
        sessionId &&
        !isPersistedPlatformSession(sessionId, sessions)
      ) {
        setDraftTitle(sessionTitleFromUserContent(message.content));
      }
      chatProps.onMessageReceived?.(message);
    },
    [chatProps, sessionId, sessions]
  );

  const handleToggleSessions = useCallback(() => {
    setConfirmingDeleteId(null);
    setHistoryOpen((open) => !open);
  }, []);

  const handleToggleFullscreen = useCallback(() => {
    setIsFullscreen((open) => !open);
  }, []);

  const handleClose = useCallback(() => {
    setCollapsed(true);
    setIsFullscreen(false);
    setAppMenuOpen(false);
    onClose?.();
  }, [onClose]);

  const handleOpen = useCallback(() => {
    setHasOpened(true);
    setCollapsed(false);
  }, []);

  useEffect(() => {
    if (collapsed || !isFullscreen) return undefined;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setIsFullscreen(false);
      }
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [collapsed, isFullscreen]);

  const sessionCustomData = useMemo(
    () => (sessionId ? { session_id: sessionId } : undefined),
    [sessionId]
  );

  const showLauncher = shouldShowPlatformLauncher({
    appCount: apps.length,
    canManageAgents,
  });
  const emptyApps = !loading && apps.length === 0;

  useEffect(() => {
    const width = platformDockInsetWidth({
      visible: showLauncher && !forbidden && hasOpened && !collapsed,
      fullscreen: isFullscreen,
      historyOpen,
    });
    document.documentElement.style.setProperty(WEBCHAT_DOCK_INSET_VAR, `${width}px`);
    return () => {
      document.documentElement.style.setProperty(WEBCHAT_DOCK_INSET_VAR, '0px');
    };
  }, [showLauncher, forbidden, hasOpened, collapsed, isFullscreen, historyOpen]);

  if (forbidden || !showLauncher) {
    return null;
  }

  const headerTitle = emptyApps ? '会话' : currentApp?.name || '平台助手';
  const listItems: PlatformSession[] =
    isDraftSession && sessionId ? [{ id: sessionId, title: draftTitle || '新会话' }, ...sessions] : sessions;

  return (
    <>
      {collapsed ? (
        <div ref={!hasOpened ? ref : undefined} className="fixed bottom-4 right-3 z-[1200]">
          <FabLauncher onOpen={handleOpen} />
        </div>
      ) : null}
      {hasOpened ? (
        <div
          ref={ref}
          className={
            isFullscreen
              ? 'fixed inset-0 z-[2000] flex h-full w-full flex-col overflow-hidden font-sans'
              : 'fixed bottom-0 right-0 top-0 z-[1200] flex flex-col overflow-hidden font-sans transition-[width] duration-200 ease-out'
          }
          style={{
            width: isFullscreen
              ? undefined
              : historyOpen
                ? PLATFORM_DOCK_CHAT_WIDTH + PLATFORM_HISTORY_RAIL_DOCK
                : PLATFORM_DOCK_CHAT_WIDTH,
            background: WC.white,
            borderLeft: isFullscreen ? undefined : `1px solid ${WC.dockEdge}`,
            display: collapsed ? 'none' : undefined,
          }}
          aria-hidden={collapsed}
        >
      <div ref={menuRef} className="relative flex-shrink-0">
        <div
          className="flex h-12 items-center gap-1.5 pl-4 pr-2"
          style={{
            background: WC.headerBg,
            color: WC.headerInk,
            borderBottom: `1px solid ${WC.botBorder}`,
          }}
        >
          {emptyApps ? (
            <div className="min-w-0 flex-1 truncate text-sm font-medium">会话</div>
          ) : (
            <button
              type="button"
              title="切换智能体"
              onClick={() => setAppMenuOpen((open) => !open)}
              className="flex min-w-0 flex-1 items-center gap-1 border-none bg-transparent p-0 text-left text-sm font-medium"
              style={{ color: WC.headerInk }}
            >
              <span className="truncate">{headerTitle}</span>
              <svg
                width="12"
                height="12"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                className="flex-shrink-0"
                style={{ color: WC.muted }}
              >
                <path d={appMenuOpen ? 'M18 15l-6-6-6 6' : 'M6 9l6 6 6-6'} />
              </svg>
            </button>
          )}
          {!emptyApps && (
            <>
              <QuietIcon title="新对话" onClick={handleNewChat}>
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M12 5v14M5 12h14" />
                </svg>
              </QuietIcon>
              <QuietIcon
                title={historyOpen ? '收起历史' : '历史会话'}
                onClick={handleToggleSessions}
                active={historyOpen}
              >
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M3 12a9 9 0 1 0 3-6.7" />
                  <path d="M3 4v5h5" />
                  <path d="M12 7v5l3 2" />
                </svg>
              </QuietIcon>
            </>
          )}
          {showFullscreenButton && !emptyApps && (
            <QuietIcon
              title={isFullscreen ? '退出全屏' : '全屏'}
              onClick={handleToggleFullscreen}
              active={isFullscreen}
            >
              {isFullscreen ? (
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M8 3v3a2 2 0 0 1-2 2H3m18 0h-3a2 2 0 0 1-2-2V3m0 18v-3a2 2 0 0 1 2-2h3M3 16h3a2 2 0 0 1 2 2v3" />
                </svg>
              ) : (
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M8 3H5a2 2 0 0 0-2 2v3m18 0V5a2 2 0 0 0-2-2h-3m0 18h3a2 2 0 0 0 2-2v-3M3 16v3a2 2 0 0 0 2 2h3" />
                </svg>
              )}
            </QuietIcon>
          )}
          <QuietIcon title="关闭" onClick={handleClose}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <rect x="3" y="4" width="18" height="16" rx="2" />
              <path d="M15 4v16" />
            </svg>
          </QuietIcon>
        </div>
        {appMenuOpen && !emptyApps ? (
          <div
            className="absolute left-2 right-2 top-[54px] z-20 overflow-hidden rounded-lg"
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
          style={{ background: WC.stage, color: WC.muted }}
        >
          <p className="text-sm font-medium" style={{ color: WC.botText }}>
            还没有可对话的智能体
          </p>
          <p className="mt-2 text-xs leading-[18px]">
            请先发布智能体，并在详情中开通「平台」渠道。开通后即可在这里对话。
          </p>
          {manageAgentsUrl ? (
            <a
              href={manageAgentsUrl}
              className="mt-4 inline-flex h-8 cursor-pointer items-center justify-center rounded-md px-3 text-sm font-medium no-underline hover:opacity-90"
              style={{ background: WC.indigo, color: WC.onPrimary }}
            >
              前往智能体列表
            </a>
          ) : null}
        </div>
      ) : (
        <div className="flex min-h-0 flex-1">
          {historyOpen ? (
            <HistoryRail
              items={listItems}
              sessionId={sessionId}
              loading={loading}
              wide={isFullscreen}
              onSelect={handleSelectSession}
              canDelete={(id) => !isPersistedPlatformSession(id, sessions) || Boolean(platform.deleteSessionUrl)}
              confirmingDeleteId={confirmingDeleteId}
              deletingId={deletingId}
              onRequestDelete={setConfirmingDeleteId}
              onConfirmDelete={(id) => void handleDeleteSession(id)}
              onCancelDelete={() => setConfirmingDeleteId(null)}
            />
          ) : null}
          <div className="flex min-h-0 min-w-0 flex-1 flex-col" style={{ background: WC.stage }}>
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
                  wideLayout={isFullscreen}
                  customData={sessionCustomData}
                  onStateChange={handleChatStateChange}
                  onMessageReceived={handleMessageReceived}
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
        </div>
      )}
        </div>
      ) : null}
    </>
  );
}));

PlatformChat.displayName = 'PlatformChat';

export function shouldRenderPlatformChat(props: Pick<PlatformChatProps, 'platform' | 'sseUrl'>): boolean {
  return isPlatformMode(props);
}
