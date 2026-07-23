'use client';

import React from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { useTranslation } from '@/utils/i18n';
import StepWizardFlow, {
  type StepWizardFlowStep,
} from '@/components/step-wizard-flow';
import IntegrationAccessComplete from '@/components/integration-access-complete';
import type { K3sCommandData } from '@/app/monitor/types/integration';
import AccessConfig from './accessConfig';
import CollectorInstall from './collectorInstall';

interface K3sWizardState {
  commandData: K3sCommandData | null;
}

const K3sConfiguration: React.FC = () => {
  const { t } = useTranslation();
  const router = useRouter();
  const searchParams = useSearchParams();
  const objectId = searchParams.get('id');
  const initialState: K3sWizardState = { commandData: null };

  const steps: StepWizardFlowStep<K3sWizardState>[] = [
    {
      title: t('monitor.integrations.k3s.accessConfig'),
      content: ({ state, next }) => (
        <AccessConfig
          commandData={state.commandData}
          onNext={(commandData) =>
            next({ commandData })
          }
        />
      ),
    },
    {
      title: t('monitor.integrations.k3s.collectorInstall'),
      content: ({ state, prev, next }) => (
        <CollectorInstall
          commandData={state.commandData}
          onPrev={prev}
          onNext={() => next()}
        />
      ),
    },
    {
      title: t('monitor.integrations.k3s.accessComplete'),
      content: ({ reset }) => (
        <IntegrationAccessComplete
          title={t('monitor.integrations.k3s.accessCompleteTitle')}
          description={t('monitor.integrations.k3s.accessCompleteDesc')}
          subDescription={t('monitor.integrations.k3s.accessCompleteSubDesc')}
          actions={[
            {
              key: 'clusters',
              type: 'primary',
              label: t('monitor.integrations.k3s.viewClusterList'),
              onClick: () =>
                router.push(`/monitor/integration/asset?objId=${objectId}`),
            },
            {
              key: 'reset',
              label: t('monitor.integrations.k3s.addAnotherCluster'),
              onClick: () => reset(initialState),
            },
          ]}
        />
      ),
    },
  ];

  return (
    <StepWizardFlow
      className="w-full"
      initialState={initialState}
      steps={steps}
    />
  );
};

export default K3sConfiguration;
