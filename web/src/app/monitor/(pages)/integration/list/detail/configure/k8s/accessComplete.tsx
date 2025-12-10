'use client';
import React from 'react';
import { Button } from 'antd';
import { useRouter, useSearchParams } from 'next/navigation';
import { useTranslation } from '@/utils/i18n';
import Icon from '@/components/icon';
import { AccessCompleteProps } from '@/app/monitor/types/integration';

const AccessComplete: React.FC<AccessCompleteProps> = ({ onReset }) => {
  const { t } = useTranslation();
  const router = useRouter();
  const params = useSearchParams();

  const handleViewMetrics = () => {
    // 跳转到集群监控页面
    const objId = params.get('id');
    router.push(`/monitor/integration/asset?objId=${objId}`);
  };

  const handleAddAnother = () => {
    // 重新开始接入流程，返回第一步
    onReset();
  };

  return (
    <div>
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
              {t('monitor.integrations.k8s.accessCompleteTitle')}
            </h3>
          </div>
          <p className="text-lg mb-3 leading-relaxed">
            {t('monitor.integrations.k8s.accessCompleteDesc')}
          </p>
          <p className="text-base text-[var(--color-text-3)] leading-relaxed">
            {t('monitor.integrations.k8s.accessCompleteSubDesc')}
          </p>
        </div>
        <div className="flex justify-center mb-[10px]">
          <Button type="primary" onClick={handleViewMetrics}>
            {t('monitor.integrations.k8s.viewClusterList')}
          </Button>
          <Button onClick={handleAddAnother} className="ml-[10px]">
            {t('monitor.integrations.k8s.addAnotherCluster')}
          </Button>
        </div>
      </div>
    </div>
  );
};

export default AccessComplete;
