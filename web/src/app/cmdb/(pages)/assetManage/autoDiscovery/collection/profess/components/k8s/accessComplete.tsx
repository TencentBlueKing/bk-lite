'use client';
import React from 'react';
import { Button, Result } from 'antd';
import { useTranslation } from '@/utils/i18n';

interface Props {
  onReset: () => void;
  onClose: () => void;
}

/**
 * CMDB 引导式接入第三步：明确区分「采集器已上报」与「CMDB 资源已落图」两个语义。
 */
const AccessComplete: React.FC<Props> = ({ onReset, onClose }) => {
  const { t } = useTranslation();
  return (
    <Result
      status="success"
      title={t('Collection.k8sTask.accessCompleteTitle') || 'Collector setup completed'}
      subTitle={
        t('Collection.k8sTask.accessCompleteDesc') ||
        'The collector is reporting to VictoriaMetrics. CMDB will materialize k8s resources (nodes / pods / workloads / namespaces) on the configured schedule. Open the task detail to trigger a one-off run if needed.'
      }
      extra={[
        <Button type="primary" key="done" onClick={onClose}>
          {t('common.done') || 'Done'}
        </Button>,
        <Button key="another" onClick={onReset}>
          {t('Collection.k8sTask.addAnotherCluster') || 'Add another cluster'}
        </Button>,
      ]}
    />
  );
};

export default AccessComplete;
