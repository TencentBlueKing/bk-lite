'use client';

import React from 'react';
import { useRouter } from 'next/navigation';
import { useTranslation } from '@/utils/i18n';
import IntegrationK8sConfigurationShell from '@/components/integration-k8s-configuration-shell';
import { createLogK8sAccessCompletePreset } from '@/components/integration-access-complete';
import AccessConfig from './accessConfig';
import CollectorInstall from './collectorInstall';

export interface K8sCommandData {
  command?: string;
  cloud_region_id?: React.Key;
  instance_id?: string;
  runtime_profile?: 'standard' | 'docker' | 'custom';
  host_log_path?: string;
  docker_container_log_path?: string;
}

const K8sConfiguration: React.FC = () => {
  const { t } = useTranslation();
  const router = useRouter();

  return (
    <IntegrationK8sConfigurationShell<K8sCommandData>
      className="w-full"
      accessConfigTitle={t('log.integration.k8s.accessConfig')}
      collectorInstallTitle={t('log.integration.k8s.collectorInstall')}
      accessCompleteTitle={t('log.integration.k8s.accessComplete')}
      accessCompletePreset={createLogK8sAccessCompletePreset(t, {
        onPrimaryAction: () => router.push('/log/integration/receive'),
        onSecondaryAction: () => undefined,
      })}
      renderAccessConfig={({ commandData, next }) => (
        <AccessConfig commandData={commandData} onNext={next} />
      )}
      renderCollectorInstall={({ commandData, prev, next }) => (
        <CollectorInstall
          commandData={commandData}
          onPrev={prev}
          onNext={next}
        />
      )}
    />
  );
};

export default K8sConfiguration;
