'use client';

import { useCallback, useEffect, useRef } from 'react';
import { InfiniteScroll, Tabs } from 'antd-mobile';
import { SearchOutline } from 'antd-mobile-icons';
import { useRouter } from 'next/navigation';
import MobilePageHeader from '@/components/mobile-page-header';
import MobilePullToRefresh from '@/components/mobile-pull-to-refresh';
import MobileTabShell from '@/components/mobile-tab-shell';
import { MobileResult, MobileSkeleton } from '@/components/mobile-feedback';
import { AlertCard } from '@/features/todo/alert-card';
import {
  formatAlertCount,
  TODO_PAGE_SIZE,
  type TodoAlert,
  type TodoViewKey,
} from '@/features/todo/model';
import { useAlertFeed, type AlertFeedViewState } from '@/features/todo/use-alert-feed';
import { useAuth } from '@/context/auth';
import {
  clearMobileViewStale,
  isMobileViewStale,
  readMobileViewSnapshot,
  restoreMobileViewScroll,
  writeMobileViewSnapshot,
} from '@/navigation/mobile-view-cache';
import { shouldShowListPagination } from '@/utils/listPagination';
import { getCurrentTeamCookie } from '@/utils/teamCookie';
import { useTranslation } from '@/utils/i18n';
import styles from '@/features/todo/todo.module.css';

interface TodoRootViewState {
  feed: AlertFeedViewState;
}

function TabLabel({
  label,
  count,
  ready,
}: {
  label: string;
  count: number;
  ready: boolean;
}) {
  const badge = ready ? formatAlertCount(count) : '';
  return (
    <span className={styles.tabTitle}>
      <span>{label}</span>
      {badge ? <span className={styles.tabBadge}>{badge}</span> : null}
    </span>
  );
}

export default function TodoPage() {
  const { t } = useTranslation();
  const { userInfo } = useAuth();
  const router = useRouter();
  const cacheScope = `${userInfo?.id || 0}:${getCurrentTeamCookie() || 'none'}`;
  const initialSnapshot = useRef(readMobileViewSnapshot<TodoRootViewState>(cacheScope, 'todo-root'));
  const shouldRevalidate = useRef(
    Boolean(initialSnapshot.current) && isMobileViewStale(cacheScope, 'todo-root'),
  );
  const controller = useAlertFeed(initialSnapshot.current?.data.feed);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const levelMap = new Map(controller.levels.map((level) => [String(level.levelId), level]));
  const highUnavailable = controller.activeView === 'high' && controller.levelStatus === 'error';
  const loading = controller.feed.status === 'loading'
    || (controller.activeView === 'high' && controller.levelStatus === 'loading');

  const saveSnapshot = useCallback((scrollTop = scrollRef.current?.scrollTop || 0) => {
    if (controller.feed.status !== 'ready') return;
    writeMobileViewSnapshot<TodoRootViewState>(cacheScope, 'todo-root', {
      feed: controller.viewState,
    }, scrollTop);
  }, [cacheScope, controller.feed.status, controller.viewState]);

  useEffect(() => {
    saveSnapshot();
  }, [saveSnapshot]);

  useEffect(() => {
    restoreMobileViewScroll(scrollRef.current, initialSnapshot.current?.scrollTop);
  }, []);

  useEffect(() => {
    if (shouldRevalidate.current) {
      shouldRevalidate.current = false;
      void controller.revalidate().then((ok) => {
        if (ok) clearMobileViewStale(cacheScope, 'todo-root');
      });
      return;
    }
    // 无可用 snapshot 时本身会重新拉数，清掉遗留失效标记。
    if (!initialSnapshot.current && isMobileViewStale(cacheScope, 'todo-root')) {
      clearMobileViewStale(cacheScope, 'todo-root');
    }
  }, [cacheScope, controller.revalidate]);

  const viewTitle = (view: TodoViewKey, label: string) => {
    const feed = controller.feeds[view];
    return (
      <TabLabel
        label={label}
        count={feed.count}
        ready={feed.status === 'ready'}
      />
    );
  };

  const renderCard = (alert: TodoAlert) => (
    <AlertCard
      key={alert.id}
      alert={alert}
      level={levelMap.get(alert.levelId)}
      statusLabel={t(`todo.status.${alert.status}`, alert.status || '--')}
      operatorLabel={t('todo.fields.operator')}
      onOpen={() => router.push(`/todo/alerts/detail?id=${alert.id}`)}
    />
  );

  return (
    <MobileTabShell activeTab="todo">
      <main className={styles.page}>
        <MobilePageHeader title={t('todo.title')} actions={[{
          href: '/todo/search', icon: <SearchOutline aria-hidden="true" />, label: t('todo.searchAlerts'),
        }]} />
        <div className={styles.filterBar}>
          <Tabs
            className={styles.tabs}
            activeKey={controller.activeView}
            onChange={(key) => controller.setActiveView(key as TodoViewKey)}
          >
            <Tabs.Tab title={viewTitle('mine', t('todo.views.mine'))} key="mine" />
            <Tabs.Tab title={viewTitle('high', t('todo.views.high'))} key="high" />
            <Tabs.Tab title={viewTitle('open', t('todo.views.open'))} key="open" />
          </Tabs>
        </div>
        <div className={styles.scroll} ref={scrollRef} onScroll={(event) => saveSnapshot(event.currentTarget.scrollTop)}>
          <MobilePullToRefresh disabled={loading || highUnavailable} onRefresh={controller.refresh}>
            <div className={styles.refreshContent}>
              {loading && controller.feed.items.length === 0 ? (
                <MobileSkeleton label={t('common.loading')} variant="list" rows={5} />
              ) : highUnavailable || controller.feed.status === 'error' ? (
                <MobileResult
                  kind={highUnavailable ? 'permission' : 'error'}
                  title={highUnavailable ? t('todo.levelPermissionDenied') : t('todo.loadFailed')}
                  description={t('todo.retryHint')}
                  actionLabel={t('common.retry')}
                  onAction={() => void controller.retry().catch(() => undefined)}
                />
              ) : controller.feed.items.length === 0 ? (
                <MobileResult kind="empty" title={t('todo.empty')} description={t('todo.emptyHint')} />
              ) : (
                <div className={styles.alertList}>
                  {controller.feed.items.map((alert) => renderCard(alert))}
                  {shouldShowListPagination(
                    controller.feed.count,
                    controller.feed.items.length,
                    TODO_PAGE_SIZE,
                  ) && (
                    <InfiniteScroll
                      loadMore={controller.loadMore}
                      hasMore={controller.feed.items.length < controller.feed.count}
                    />
                  )}
                </div>
              )}
            </div>
          </MobilePullToRefresh>
        </div>
      </main>
    </MobileTabShell>
  );
}
