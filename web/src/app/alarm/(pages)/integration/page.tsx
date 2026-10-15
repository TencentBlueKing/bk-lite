'use client';

import React, { useState, useEffect } from 'react';
import { Skeleton } from 'antd';
import CompactEmptyState from '@/components/compact-empty-state';
import PermissionWrapper from '@/components/permission';
import ListPageHeader from '@/components/list-page-header';
import CardGridSkeleton from '@/components/card-grid-skeleton';
import { useSourceApi } from '@/app/alarm/api/integration';
import { useTranslation } from '@/utils/i18n';
import { SourceItem } from '@/app/alarm/types/integration';
import SummaryStats from './components/SummaryStats';
import IntegrationCard from './components/IntegrationCard';

interface DailyEventStats {
  today_count: number;
  yesterday_count: number;
}

const IntegrationPage: React.FC = () => {
  const { getAlertSources, getDailyEventStats } = useSourceApi();
  const [sources, setSources] = useState<SourceItem[]>([]);
  const [dailyStats, setDailyStats] = useState<DailyEventStats | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const { t } = useTranslation();

  useEffect(() => {
    getSourcesList();
    fetchDailyStats();
  }, []);

  const getSourcesList = async () => {
    setLoading(true);
    try {
      const res = await getAlertSources();
      if (res) {
        setSources(res);
      }
    } catch (error) {
      console.error(error);
    } finally {
      setLoading(false);
    }
  };

  const fetchDailyStats = async () => {
    try {
      const res = await getDailyEventStats();
      if (res) {
        setDailyStats(res);
      }
    } catch (error) {
      console.error(error);
    }
  };

  return (
    <div className="flex min-h-0 w-full flex-1 flex-col p-6">
      <ListPageHeader
        title={t('integration.overviewTitle')}
        description={t('integration.overviewDesc')}
      />
      {loading ? (
        <>
          <div className="mb-5 grid grid-cols-1 gap-3 sm:grid-cols-3">
            {Array.from({ length: 3 }).map((_, index) => (
              <div
                key={index}
                className="rounded-lg border border-[var(--color-border-1)] bg-[var(--color-bg)] p-3"
              >
                <Skeleton active title={{ width: '40%' }} paragraph={{ rows: 1 }} />
              </div>
            ))}
          </div>
          <CardGridSkeleton className="grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4" />
        </>
      ) : (
        <>
          {sources.length > 0 && <SummaryStats sources={sources} dailyStats={dailyStats} />}
          {!sources.length ? (
            <div className="mt-[24vh]">
              <CompactEmptyState description={t('common.noData')} />
            </div>
          ) : (
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
              {sources.map((src: SourceItem) => (
                <PermissionWrapper key={src.id} requiredPermissions={['Detail']}>
                  <IntegrationCard src={src} />
                </PermissionWrapper>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
};

export default IntegrationPage;
