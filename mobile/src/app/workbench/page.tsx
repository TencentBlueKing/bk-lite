'use client';

import React, { useState, useRef, useEffect, useCallback } from 'react';
import { MessageOutline } from 'antd-mobile-icons';
import { useRouter } from 'next/navigation';
import Image from 'next/image';
import { useTranslation } from '@/utils/i18n';
import {
  ChatApplicationItem,
  GetApplicationsParams,
  getApplication,
  getApplicationItems,
} from '@/api/bot';
import { getAvatar } from '@/utils/avatar';
import { getAppTagClassKey, getAppTagLabel } from '@/constants/workbenchTags';
import MobileTabShell from '@/components/mobile-tab-shell';
import MobilePageHeader from '@/components/mobile-page-header';
import MobilePullToRefresh from '@/components/mobile-pull-to-refresh';
import MobileListCard from '@/components/mobile-list-card';
import MobileSegmentTabs from '@/components/mobile-segment-tabs';
import { MobileResult, MobileSkeleton } from '@/components/mobile-feedback';
import { buildConversationHref } from '@/utils/conversationRoute';
import styles from '@/features/workbench/workbench.module.css';

type TabKey =
  | 'all'
  | 'routine_ops'
  | 'monitor_alarm'
  | 'automation'
  | 'security_audit'
  | 'performance_analysis'
  | 'ops_plan';

export default function WorkbenchPage() {
  const { t } = useTranslation();
  const router = useRouter();
  const [activeTab, setActiveTab] = useState<TabKey>('all');
  const [botList, setBotList] = useState<ChatApplicationItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [loadFailed, setLoadFailed] = useState(false);
  const abortControllerRef = useRef<AbortController | null>(null);

  const tabItems = [
    { key: 'all' as TabKey, title: t('workbench.all') },
    { key: 'routine_ops' as TabKey, title: t('workbench.routineOps') },
    { key: 'monitor_alarm' as TabKey, title: t('workbench.monitorAlarm') },
    { key: 'automation' as TabKey, title: t('workbench.automation') },
    { key: 'security_audit' as TabKey, title: t('workbench.securityAudit') },
    { key: 'performance_analysis' as TabKey, title: t('workbench.performanceAnalysis') },
    { key: 'ops_plan' as TabKey, title: t('workbench.opsPlan') },
  ];

  const fetchApplications = useCallback(async (
    tabKey: TabKey,
    options: Pick<GetApplicationsParams, 'page' | 'page_size'> & { preserveContent?: boolean } = {},
  ) => {
    const { preserveContent = false, ...params } = options;
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }

    const controller = new AbortController();
    abortControllerRef.current = controller;

    if (!preserveContent) {
      setLoading(true);
      setLoadFailed(false);
    }

    try {
      const requestParams: GetApplicationsParams = {
        page: params?.page || 1,
        page_size: params?.page_size || 20,
      };

      if (tabKey !== 'all') {
        requestParams.app_tags = tabKey;
      }

      const response = await getApplication(requestParams, { signal: controller.signal });

      if (controller.signal.aborted) {
        return;
      }
      if (!response.result) {
        throw new Error(response.message || 'Failed to fetch applications');
      }
      setBotList(getApplicationItems(response));
      setLoadFailed(false);
    } catch (error: unknown) {
      if (error instanceof DOMException && error.name === 'AbortError') {
        return;
      }
      console.error('Failed to fetch applications:', error);
      if (preserveContent) {
        throw error;
      }
      setBotList([]);
      setLoadFailed(true);
    } finally {
      if (!preserveContent && !controller.signal.aborted) {
        setLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    fetchApplications(activeTab);

    return () => {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
    };
  }, [activeTab, fetchApplications]);

  const renderAppCard = (item: ChatApplicationItem) => (
    <MobileListCard
      key={item.id}
      variant="raised"
      leading={(
        <span className={styles.avatar}>
          <Image
            src={getAvatar(item.id)}
            alt=""
            width={48}
            height={48}
            className={styles.avatarImg}
          />
        </span>
      )}
      title={item.app_name}
      meta={(
        <>
          <span className={styles.description}>
            {item.app_description || t('workbench.noIntroduction')}
          </span>
          {item.app_tags && item.app_tags.length > 0 ? (
            <span className={styles.tags}>
              {item.app_tags.map((tag: string) => {
                const classKey = getAppTagClassKey(tag) as keyof typeof styles;
                return (
                  <span
                    key={tag}
                    className={`${styles.tag} ${styles[classKey] || ''}`}
                  >
                    {getAppTagLabel(tag, t)}
                  </span>
                );
              })}
            </span>
          ) : null}
        </>
      )}
      onClick={() => {
        router.push(buildConversationHref({ botId: item.bot, nodeId: item.node_id }));
      }}
    />
  );

  return (
    <MobileTabShell activeTab="apps">
      <div className={styles.page}>
        <MobilePageHeader
          title={t('navigation.apps')}
          searchType="WorkbenchPage"
          actions={[{
            href: '/conversations',
            icon: <MessageOutline aria-hidden="true" />,
            label: t('navigation.conversations'),
          }]}
        />

        <MobileSegmentTabs
          className={styles.tabs}
          activeKey={activeTab}
          onChange={(key) => setActiveTab(key as TabKey)}
        >
          {tabItems.map((item) => (
            <MobileSegmentTabs.Tab title={item.title} key={item.key} />
          ))}
        </MobileSegmentTabs>

        <div className={styles.scroll}>
          <MobilePullToRefresh
            onRefresh={() => fetchApplications(activeTab, { preserveContent: true })}
          >
            <div className={styles.refreshContent}>
              {loading ? (
                <MobileSkeleton label={t('common.loading')} variant="list" rows={5} />
              ) : loadFailed ? (
                <MobileResult
                  kind="error"
                  title={t('workbench.loadFailed')}
                  description={t('workbench.loadFailedDescription')}
                  actionLabel={t('common.retry')}
                  onAction={() => void fetchApplications(activeTab)}
                />
              ) : botList.length > 0 ? (
                botList.map((item) => renderAppCard(item))
              ) : (
                <MobileResult
                  kind="empty"
                  title={t('workbench.empty')}
                  description={t('workbench.emptyHint')}
                />
              )}
            </div>
          </MobilePullToRefresh>
        </div>
      </div>
    </MobileTabShell>
  );
}
