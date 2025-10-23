'use client';
import React, { useState, useMemo } from 'react';
import { Spin, Segmented } from 'antd';
import AutomaticConfiguration from './automatic';
import { useTranslation } from '@/utils/i18n';
import configureStyle from './index.module.scss';
import { useSearchParams } from 'next/navigation';

const Configure: React.FC = () => {
  const { t } = useTranslation();
  const searchParams = useSearchParams();
  const [pageLoading, setPageLoading] = useState<boolean>(false);
  const [activeTab, setActiveTab] = useState<string>('automatic');
  const pluginName = searchParams.get('name');

  const isK8s = useMemo(() => pluginName === 'kubernetes', [pluginName]);

  const onTabChange = (val: string) => {
    setPageLoading(false);
    setActiveTab(val);
  };

  return (
    <div className={configureStyle.configure}>
      {isK8s ? (
        t('log.integration.k8sNote')
      ) : (
        <>
          <Segmented
            className="mb-[20px]"
            value={activeTab}
            options={[
              {
                label: t('log.integration.automatic'),
                value: 'automatic',
              },
            ]}
            onChange={onTabChange}
          />
          <Spin spinning={pageLoading}>
            <AutomaticConfiguration />
          </Spin>
        </>
      )}
    </div>
  );
};

export default Configure;
