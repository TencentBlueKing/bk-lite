'use client';

import React, { useState, useEffect } from 'react';
import { Spin, Empty } from 'antd';
import PermissionWrapper from '@/components/permission';
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
    <div className="w-full flex-1 min-h-0">
      <Spin spinning={loading}>
        <div className="w-full p-[24px_28px_32px]">
          {/* Page header */}
          <div className="mb-5">
            <h1 className="text-xl font-semibold text-[var(--color-text-1)] m-0">
              {t('integration.overviewTitle')}
            </h1>
            <p className="text-[13px] text-[var(--color-text-3)] mt-1 mb-0">
              {t('integration.overviewDesc')}
            </p>
          </div>

          {/* Summary stats */}
          {sources.length > 0 && <SummaryStats sources={sources} dailyStats={dailyStats} />}

          {/* Card grid or empty state */}
          {!sources.length && !loading ? (
            <div className="mt-[24vh]">
              <Empty description={t('common.noData')} />
            </div>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
              {sources.map((src: SourceItem) => (
                <PermissionWrapper key={src.id} requiredPermissions={['Detail']}>
                  <IntegrationCard src={src} />
                </PermissionWrapper>
              ))}
            </div>
          )}
        </div>
      </Spin>
    </div>
  );
};

export default IntegrationPage;
