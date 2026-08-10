'use client';

import React from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { useTranslation } from '@/utils/i18n';
import IntegrationK8sConfigurationShell from '@/components/integration-k8s-configuration-shell';
import { createMonitorK8sAccessCompletePreset } from '@/components/integration-access-complete';
import type { K8sCommandData } from '@/app/monitor/types/integration';
import AccessConfig from './accessConfig';
import CollectorInstall from './collectorInstall';

const K8sConfiguration: React.FC = () => {
  const { t } = useTranslation();
  const router = useRouter();
  const searchParams = useSearchParams();

  return (
    <IntegrationK8sConfigurationShell<K8sCommandData>
      className="w-full"
      accessConfigTitle={t('monitor.integrations.k8s.accessConfig')}
      collectorInstallTitle={t('monitor.integrations.k8s.collectorInstall')}
      accessCompleteTitle={t('monitor.integrations.k8s.accessComplete')}
      accessCompletePreset={createMonitorK8sAccessCompletePreset(t, {
        onPrimaryAction: () => {
          const objectId = searchParams.get('id');
          router.push(`/monitor/integration/asset?objId=${objectId}`);
        },
        onSecondaryAction: () => undefined,
      })}
      renderAccessConfig={({ commandData, next }) => (
        <AccessConfig commandData={commandData ?? undefined} onNext={next} />
      )}
      renderCollectorInstall={({ commandData, prev, next }) => (
        <CollectorInstall
          commandData={commandData ?? undefined}
          onPrev={prev}
          onNext={() => next()}
        />
      )}
    />
  );
};

export default K8sConfiguration;
