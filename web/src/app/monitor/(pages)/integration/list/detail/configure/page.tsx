'use client';
import React, { useMemo } from 'react';
import AutomaticConfiguration from './automatic';
import { useSearchParams } from 'next/navigation';
import configureStyle from './index.module.scss';
import { useObjectConfigInfo } from '@/app/monitor/hooks/integration/common/getObjectConfig';
import K8sConfiguration from './k8s/k8sConfiguration';
import CustomApiAccess from './customApi';

const Configure: React.FC = () => {
  const searchParams = useSearchParams();
  const { getCollectType } = useObjectConfigInfo();
  const pluginName = searchParams.get('plugin_name') || '';
  const objectName = searchParams.get('name') || '';
  const templateType = searchParams.get('template_type') || '';

  const isK8s = useMemo(() => {
    return getCollectType(objectName, pluginName) === 'k8s';
  }, [pluginName, objectName]);

  return (
    <>
      {templateType === 'custom_api' ? (
        <div className={configureStyle.configure}>
          <CustomApiAccess />
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
