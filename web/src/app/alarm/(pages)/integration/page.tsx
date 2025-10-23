'use client';

import React, { useState, useEffect } from 'react';
import PermissionWrapper from '@/components/permission';
import { useSourceApi } from '@/app/alarm/api/integration';
import { Spin, Empty } from 'antd';
import { useRouter } from 'next/navigation';
import { useTranslation } from '@/utils/i18n';
import { SourceItem } from '@/app/alarm/types/integration';

const IntegrationPage: React.FC = () => {
  const { getAlertSources } = useSourceApi();
  const [sources, setSources] = useState<SourceItem[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const { t } = useTranslation();
  const router = useRouter();

  useEffect(() => {
    getSourcesList();
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

  return (
    <div className="w-full flex-1 h-[calc(100vh-56px)] overflow-y-auto">
      <Spin spinning={loading}>
        {!sources.length ? (
          <div className="mt-[24vh]">
            {!loading && <Empty description={t('common.noData')} />}
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 2xl:grid-cols-5 gap-6">
            {sources.map((src: SourceItem) => (
              <PermissionWrapper key={src.id} requiredPermissions={['Detail']}>
                <div
                  className="p-4 rounded-xl relative shadow-md hover:shadow-lg transition-shadow cursor-pointer bg-[var(--color-bg-1)]"
                  onClick={() =>
                    router.push(
                      `/alarm/integration/detail?sourceItemId=${src.id}`
                    )
                  }
                >
                  {/* header 区域 */}
                  <div className="flex items-center mb-4">
                    <div className="flex items-center gap-3 p-[6px] bg-[#99aaf2] rounded">
                      <img
                        src={src.logo || ''}
                        alt={src.description}
                        className="w-7 h-7"
                      />
                    </div>
                    <span className="font-semibold text-base truncate ml-2">
                      {src.name}
                    </span>
                  </div>
                  {/* 信息区 */}
                  <div className="text-xs text-[var(--color-text-3)] space-y-2">
                    <div>
                      {t('alarms.eventCount')}：
                      {[undefined, null, ''].includes(src.event_count as any)
                        ? '--'
                        : src.event_count}
                    </div>
                    <div>
                      {t('alarms.lastEventTime')}：{src.last_event_time || '--'}
                    </div>
                  </div>
                </div>
              </PermissionWrapper>
            ))}
          </div>
        )}
      </Spin>
    </div>
  );
};

export default IntegrationPage;
