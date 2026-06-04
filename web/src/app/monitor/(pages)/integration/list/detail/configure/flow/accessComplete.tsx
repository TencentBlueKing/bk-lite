'use client';

import React from 'react';
import { Button } from 'antd';
import { useRouter, useSearchParams } from 'next/navigation';
import { useTranslation } from '@/utils/i18n';
import Icon from '@/components/icon';

interface AccessCompleteProps {
  onReset: () => void;
}

const AccessComplete: React.FC<AccessCompleteProps> = ({ onReset }) => {
  const { t } = useTranslation();
  const router = useRouter();
  const params = useSearchParams();
  const objectId = params.get('id') || params.get('objId') || '';

  const handleViewMonitorView = () => {
    router.push(`/monitor/view`);
  };

  const handleBackToTemplateList = () => {
    router.push(`/monitor/integration/list?objId=${objectId}`);
  };

  return (
    <div className="text-center p-[20px]">
      <div className="mb-6">
        <div className="mx-auto flex items-center justify-center">
          <Icon type="yunhangzhongx" className="text-8xl" />
        </div>
      </div>
      <div className="mb-6">
        <div className="flex items-center justify-center mb-4">
          <Icon type="finish" className="text-4xl mr-2" />
          <h3 className="text-2xl font-bold text-gray-900">
            {t('monitor.integrations.flow.accessCompleteTitle')}
          </h3>
        </div>
        <p className="text-lg mb-3 leading-relaxed">
          {t('monitor.integrations.flow.accessCompleteDesc')}
        </p>
        <p className="text-base text-[var(--color-text-3)] leading-relaxed">
          {t('monitor.integrations.flow.accessCompleteSubDesc')}
        </p>
      </div>
      <div className="flex justify-center flex-wrap gap-[10px]">
        <Button type="primary" onClick={handleViewMonitorView}>
          {t('monitor.integrations.flow.viewAssetList')}
        </Button>
        <Button onClick={onReset}>
          {t('monitor.integrations.flow.addAnotherAsset')}
        </Button>
        <Button onClick={handleBackToTemplateList}>
          {t('monitor.integrations.flow.backToTemplateList')}
        </Button>
      </div>
    </div>
  );
};

export default AccessComplete;
