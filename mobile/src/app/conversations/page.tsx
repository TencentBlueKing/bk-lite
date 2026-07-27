'use client';

import { useCallback, useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import Image from 'next/image';
import { ErrorBlock, InfiniteScroll, SpinLoading, SwipeAction } from 'antd-mobile';
import { MessageOutline, MoreOutline } from 'antd-mobile-icons';
import MobileTabShell from '@/components/mobile-tab-shell';
import MobilePageHeader from '@/components/mobile-page-header';
import MobilePullToRefresh from '@/components/mobile-pull-to-refresh';
import { getMobileSessions } from '@/api/bot';
import { useSessionDeletion } from '@/app/conversation/hooks';
import { getAppTagLabel } from '@/constants/workbenchTags';
import { useLocale } from '@/context/locale';
import { SessionItem } from '@/types/conversation';
import { getAvatar } from '@/utils/avatar';
import { useTranslation } from '@/utils/i18n';
import { buildConversationHref } from '@/utils/conversationRoute';
import {
  hasMoreSessions,
  mergeSessionItems,
  MOBILE_SESSION_PAGE_SIZE,
  shouldShowSessionPagination,
} from '@/utils/sessionPagination';
import { formatSessionActivity } from './session-time';
import styles from './page.module.css';

export default function ConversationsPage() {
  const router = useRouter();
  const { t } = useTranslation();
  const { locale } = useLocale();
  const [sessions, setSessions] = useState<SessionItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadFailed, setLoadFailed] = useState(false);
  const [sessionCount, setSessionCount] = useState(0);
  const [nextPage, setNextPage] = useState(1);

  const loadSessions = useCallback(async ({
    append = false,
    page = 1,
    preserveContent = false,
  } = {}) => {
    if (!preserveContent) {
      setLoading(true);
      setLoadFailed(false);
    }

    try {
      const response = await getMobileSessions({ page, page_size: MOBILE_SESSION_PAGE_SIZE });
      const items = response.data?.items;
      if (!response?.result || !items) {
        throw new Error(response?.message || 'Failed to load conversations');
      }
      setSessions((currentSessions) => (
        append ? mergeSessionItems(currentSessions, items) : items
      ));
      setSessionCount(response.data?.count ?? items.length);
      setNextPage(page + 1);
      setLoadFailed(false);
    } catch (error) {
      console.error('Failed to load conversations:', error);
      if (preserveContent) {
        throw error;
      }
      setLoadFailed(true);
    } finally {
      if (!preserveContent) {
        setLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    void loadSessions();
  }, [loadSessions]);

  const openSession = (session: SessionItem) => {
    router.push(buildConversationHref({
      botId: session.bot_id,
      sessionId: session.session_id,
      nodeId: session.node_id,
    }));
  };

  const handleSessionDeleted = useCallback(async () => {
    await loadSessions();
  }, [loadSessions]);
  const { confirmDeleteSession, deletingSessionId, openSessionActions } = useSessionDeletion({
    onDeleted: handleSessionDeleted,
  });
  const loadMoreSessions = useCallback(() => loadSessions({
    append: true,
    page: nextPage,
    preserveContent: true,
  }), [loadSessions, nextPage]);

  return (
    <MobileTabShell activeTab="apps">
      <div className={styles.page}>
        <MobilePageHeader
          title={t('navigation.conversations')}
          searchType="ConversationList"
          backHref="/workbench"
        />

        <main className={styles.content}>
          <MobilePullToRefresh onRefresh={() => loadSessions({ preserveContent: true })}>
            <div className={styles.refreshContent}>
              {loading && (
                <div className={`${styles.state} ${styles.loadingState}`}>
                  <SpinLoading color="primary" />
                </div>
              )}

              {!loading && loadFailed && (
                <div className={styles.state}>
                  <ErrorBlock
                    status="disconnected"
                    title={t('conversations.loadFailed')}
                    description={t('conversations.loadFailedDescription')}
                  >
                    <button type="button" className={styles.stateAction} onClick={() => void loadSessions()}>
                      {t('common.retry')}
                    </button>
                  </ErrorBlock>
                </div>
              )}

              {!loading && !loadFailed && sessions.length === 0 && (
                <div className={styles.state}>
                  <ErrorBlock
                    status="empty"
                    title={t('conversations.emptyTitle')}
                    description={t('conversations.emptyDescription')}
                  >
                    <button
                      type="button"
                      className={styles.stateAction}
                      onClick={() => router.replace('/workbench')}
                    >
                      {t('conversations.exploreApps')}
                    </button>
                  </ErrorBlock>
                </div>
              )}

              {!loading && !loadFailed && sessions.length > 0 && (
                <div className={styles.sessionList}>
                  {sessions.map((session) => {
                    const activityTime = session.updated_at || session.created_at;
                    const isDeleting = deletingSessionId === session.session_id;
                    const applicationMeta = [
                      session.app_name,
                      ...(session.app_tags || []).map((tag) => getAppTagLabel(tag, t)),
                    ].filter(Boolean).join(' · ');

                    return (
                      <SwipeAction
                        key={session.session_id}
                        className={styles.sessionSwipe}
                        rightActions={session.node_id ? [{
                          key: 'delete',
                          text: isDeleting
                            ? <SpinLoading style={{ '--size': '16px' }} color="white" />
                            : t('common.delete'),
                          color: 'danger',
                          onClick: () => confirmDeleteSession(session),
                        }] : []}
                      >
                        <div className={styles.sessionRow}>
                          <button
                            type="button"
                            className={styles.sessionMain}
                            onClick={() => openSession(session)}
                          >
                            <span className={styles.sessionAvatar}>
                              {session.app_id ? (
                                <Image
                                  src={getAvatar(session.app_id)}
                                  alt=""
                                  width={40}
                                  height={40}
                                />
                              ) : (
                                <MessageOutline aria-hidden="true" />
                              )}
                            </span>
                            <span className={styles.sessionCopy}>
                              <span className={styles.sessionTitleRow}>
                                <span className={styles.sessionTitle}>
                                  {session.title || t('conversations.untitled')}
                                </span>
                                {activityTime && (
                                  <time className={styles.sessionTime} dateTime={activityTime}>
                                    {formatSessionActivity(activityTime, locale, t('common.yesterday'))}
                                  </time>
                                )}
                              </span>
                              <span className={styles.sessionMeta}>
                                {applicationMeta || t('conversations.sessionHint')}
                              </span>
                            </span>
                          </button>
                          {session.node_id && (
                            <button
                              type="button"
                              className={styles.sessionActions}
                              aria-label={t('chat.conversationActions')}
                              disabled={isDeleting}
                              onClick={() => openSessionActions(session)}
                            >
                              {isDeleting
                                ? <SpinLoading style={{ '--size': '16px' }} color="primary" />
                                : <MoreOutline aria-hidden="true" />}
                            </button>
                          )}
                        </div>
                      </SwipeAction>
                    );
                  })}
                  {shouldShowSessionPagination(sessionCount, sessions.length) && (
                    <InfiniteScroll
                      loadMore={loadMoreSessions}
                      hasMore={hasMoreSessions(sessions, sessionCount)}
                    />
                  )}
                </div>
              )}
            </div>
          </MobilePullToRefresh>
        </main>
      </div>
    </MobileTabShell>
  );
}
