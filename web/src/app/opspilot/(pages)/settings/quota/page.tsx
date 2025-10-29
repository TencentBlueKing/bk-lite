'use client';
import React, { useEffect, useState } from 'react';
import { Spin } from 'antd';
import CustomProgressBar from './customProgressBar';
import TopSection from '@/components/top-section';
import { useTranslation } from '@/utils/i18n';
import { QuotaData } from '@/app/opspilot/types/settings';
import { useQuotaApi } from '@/app/opspilot/api/settings';

const QuotaUsage: React.FC = () => {
  const { t } = useTranslation();
  const [data, setData] = useState<QuotaData[]>([]);
  const [loading, setLoading] = useState(true);
  const { fetchMyQuota } = useQuotaApi();

  useEffect(() => {
    const fetchData = async () => {
      setLoading(true);
      try {
        const res = await fetchMyQuota();
        const formattedData: QuotaData[] = [
          {
            label: `${t('settings.myQuota.knowledgeBase')} (${res.is_file_uniform ? t('settings.myQuota.uniform') : t('settings.myQuota.shared')})`,
            usage: res.used_file_size,
            total: res.all_file_size,
            unit: 'M'
          },
          {
            label: `${t('settings.myQuota.skills')} (${res.is_skill_uniform ? t('settings.myQuota.uniform') : t('settings.myQuota.shared')})`,
            usage: res.used_skill_count,
            total: res.all_skill_count,
            unit: ''
          },
          {
            label: `${t('settings.myQuota.bots')} (${res.is_bot_uniform ? t('settings.myQuota.uniform') : t('settings.myQuota.shared')})`,
            usage: res.used_bot_count,
            total: res.all_bot_count,
            unit: ''
          },
        ];
        setData(formattedData);
      } catch (error) {
        console.error(`${t('common.fetchFailed')}:`, error);
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, []);

  return (
    <div>
      <div className="mb-4">
        <TopSection
          title={t('settings.myQuota.title')}
          content={t('settings.myQuota.content')}
        />
      </div>
      <section
        className="bg-[var(--color-bg)] p-4 rounded-md flex overflow-auto"
        style={{ height: 'calc(100vh - 240px)' }}
      >
        <div className="flex-1">
          {loading ? (
            <div className="flex justify-center items-center h-full">
              <Spin />
            </div>
          ) : (
            <>
              <h2 className="mb-4">{t('settings.myQuota.usage')}</h2>
              {data.map((item, index) => (
                <CustomProgressBar
                  key={index}
                  label={item.label}
                  usage={item.usage}
                  total={item.total}
                  unit={item.unit}
                />
              ))}
            </>
          )}
        </div>
      </section>
    </div>
  );
};

export default QuotaUsage;
