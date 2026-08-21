'use client';
import React, { useMemo } from 'react';
import { Alert, Spin } from 'antd';
import AutomaticConfiguration from './automatic';
import { useSearchParams } from 'next/navigation';
import configureStyle from './index.module.scss';
import { useObjectConfigInfo } from '@/app/monitor/hooks/integration/common/getObjectConfig';
import K8sConfiguration from './k8s/k8sConfiguration';
import K3sConfiguration from './k3s/k3sConfiguration';
import type { FlowProtocol } from '@/app/monitor/types/integration';
import FlowConfiguration from './flow/flowConfiguration';
import TemplateAccessGuide from './accessGuide/index';
import { parseIntegrationObjectId } from '@/app/monitor/utils/integrationEntryContext';
import { useTranslation } from '@/utils/i18n';

const Configure: React.FC = () => {
  const searchParams = useSearchParams();
  const { t } = useTranslation();
  const pluginName = searchParams.get('plugin_name') || '';
  const objectName = searchParams.get('name') || '';
  const objectId = parseIntegrationObjectId(searchParams.get('id'));
  const pluginId = parseIntegrationObjectId(searchParams.get('plugin_id'));
  const templateType = searchParams.get('template_type') || '';
  const { getCollectType, ready: objectConfigReady } = useObjectConfigInfo(objectName);

  const collectType = useMemo(
    () => (objectConfigReady ? getCollectType(objectName, pluginName) : undefined),
    [getCollectType, objectConfigReady, objectName, pluginName]
  );

  const isK8s = collectType === 'k8s';
  const isK3s = collectType === 'k3s';
  const isFlow = collectType === 'netflow' || collectType === 'sflow';

  if (!objectId || !objectName || !pluginId || !pluginName) {
    return (
      <div className={configureStyle.configure}>
        <Alert
          type="error"
          showIcon
          message={t('monitor.integrations.missingEntryContext')}
          description={t('monitor.integrations.missingEntryContextDescription')}
        />
      </div>
    );
  }

  if (templateType !== 'api' && !objectConfigReady) {
    return (
      <div className={`${configureStyle.configure} flex justify-center items-center`} style={{ minHeight: 200 }}>
        <Spin />
      </div>
    );
  }

  return (
    <>
      {templateType === 'api' ? (
        <div className={configureStyle.configure}>
          <TemplateAccessGuide />
        </div>
      ) : isFlow ? (
        <div className={configureStyle.configure}>
          <FlowConfiguration protocol={collectType as FlowProtocol} />
        </div>
      ) : isK3s ? (
        <div className={configureStyle.configure}>
          <K3sConfiguration />
        </div>
      ) : !isK8s ? (
        <div className={configureStyle.configure}>
          <AutomaticConfiguration />
        </div>
      ) : (
        <div className={configureStyle.configure}>
          <K8sConfiguration />
        </div>
      )}
    </>
  );
};

export default Configure;
