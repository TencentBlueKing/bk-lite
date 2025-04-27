'use client';
import React, { useState } from 'react';
import { Spin, Segmented } from 'antd';
import ManualConfiguration from './manual';
import AutomaticConfiguration from './automatic';
import { useTranslation } from '@/utils/i18n';
import configureStyle from './index.module.scss';

const Configure: React.FC = () => {
  const { t } = useTranslation();
  const [pageLoading, setPageLoading] = useState<boolean>(false);
  const [activeTab, setActiveTab] = useState<string>('manual');

  const onTabChange = (val: string) => {
    setPageLoading(false);
    setActiveTab(val);
  };

  return (
    <div className={configureStyle.configure}>
      <Segmented
        className="mb-[20px]"
        value={activeTab}
        options={[
          { label: t('monitor.intergrations.manual'), value: 'manual' },
          { label: t('monitor.intergrations.automatic'), value: 'automatic' },
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
  );
};

export default Configure;
