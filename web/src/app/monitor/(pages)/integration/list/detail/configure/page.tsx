'use client';
import React, { useState, useMemo } from 'react';
import { Spin, Segmented } from 'antd';
import ManualConfiguration from './manual';
import AutomaticConfiguration from './automatic';
import { useTranslation } from '@/utils/i18n';
import { useSearchParams } from 'next/navigation';
import configureStyle from './index.module.scss';
import { useObjectConfigInfo } from '@/app/monitor/hooks/integration/common/getObjectConfig';

const Configure: React.FC = () => {
  const { t } = useTranslation();
  const searchParams = useSearchParams();
  const { getCollectType } = useObjectConfigInfo();
  const pluginName = searchParams.get('plugin_name') || '';
  const objectName = searchParams.get('name') || '';
  const [pageLoading, setPageLoading] = useState<boolean>(false);
  const [activeTab, setActiveTab] = useState<string>('automatic');

  const onTabChange = (val: string) => {
    setPageLoading(false);
    setActiveTab(val);
  };

  const isK8s = useMemo(() => {
    return getCollectType(objectName, pluginName) === 'k8s';
  }, [pluginName, objectName]);

  return (
    <>
      {!isK8s ? (
        <div className={configureStyle.configure}>
          <Segmented
            className="mb-[20px]"
            value={activeTab}
            options={[
              {
                label: t('monitor.integrations.automatic'),
                value: 'automatic',
              },
              //   { label: t('monitor.integrations.manual'), value: 'manual' },
            ]}
            onChange={onTabChange}
          />
          <Spin spinning={pageLoading}>
            {activeTab === 'manual' ? (
              <ManualConfiguration />
            ) : (
              <AutomaticConfiguration />
            )}
          </Spin>
        </div>
      ) : (
        t('monitor.integrations.note')
      )}
    </>
  );
};

export default Configure;
