'use client';
import React, { useMemo } from 'react';
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

  const isK8s = useMemo(() => {
    return getCollectType(objectName, pluginName) === 'k8s';
  }, [pluginName, objectName]);

  return (
    <>
      {!isK8s ? (
        <div className={configureStyle.configure}>
          <AutomaticConfiguration />
        </div>
      ) : (
        t('monitor.integrations.note')
      )}
    </>
  );
};

export default Configure;
