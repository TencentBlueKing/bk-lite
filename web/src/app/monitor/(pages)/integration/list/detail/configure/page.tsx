'use client';
import React, { useMemo } from 'react';
import AutomaticConfiguration from './automatic';
import { useSearchParams } from 'next/navigation';
import configureStyle from './index.module.scss';
import { useObjectConfigInfo } from '@/app/monitor/hooks/integration/common/getObjectConfig';
import K8sConfiguration from './k8s/k8sConfiguration';
import type { FlowProtocol } from '@/app/monitor/types/integration';
import FlowConfiguration from './flow/flowConfiguration';
import TemplateAccessGuide from './accessGuide/index';

const Configure: React.FC = () => {
  const searchParams = useSearchParams();
  const { getCollectType } = useObjectConfigInfo();
  const pluginName = searchParams.get('plugin_name') || '';
  const objectName = searchParams.get('name') || '';
  const templateType = searchParams.get('template_type') || '';

  const collectType = useMemo(
    () => getCollectType(objectName, pluginName),
    [getCollectType, objectName, pluginName]
  );

  const isK8s = collectType === 'k8s';
  const isFlow = collectType === 'netflow' || collectType === 'sflow';

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
