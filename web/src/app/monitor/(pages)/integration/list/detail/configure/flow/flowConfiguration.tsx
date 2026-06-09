'use client';

import React, { useState } from 'react';
import { Steps } from 'antd';
import { useSearchParams } from 'next/navigation';
import { useTranslation } from '@/utils/i18n';
import type { FlowProtocol } from '@/app/monitor/types/integration';
import AccessAsset from './accessAsset';
import AccessGuide from './accessGuide';
import AccessComplete from './accessComplete';

export interface FlowAssetWizardState {
  accessType: 'new' | 'existing';
  instance_id: string;
  cloud_region_id: number;
  ip: string;
  name: string;
  organizations: React.Key[];
  fallback_sampling_rate: number;
  enabled_protocols?: string[];
}

interface FlowConfigurationProps {
  protocol: FlowProtocol;
}

const FlowConfiguration: React.FC<FlowConfigurationProps> = ({ protocol }) => {
  const { t } = useTranslation();
  const searchParams = useSearchParams();
  const objectId = searchParams.get('id') ? Number(searchParams.get('id')) : undefined;
  const [currentStep, setCurrentStep] = useState(0);
  const [wizardState, setWizardState] = useState<{
    asset?: FlowAssetWizardState;
  }>({});

  const handleAssetNext = (asset: FlowAssetWizardState) => {
    setWizardState({ asset });
    setCurrentStep(1);
  };

  const handleGuideNext = () => {
    setCurrentStep(2);
  };

  const handlePrev = () => {
    setCurrentStep((prev) => Math.max(prev - 1, 0));
  };

  const handleReset = () => {
    setCurrentStep(0);
    setWizardState({});
  };

  const steps = [
    {
      title: t('monitor.integrations.flow.accessAsset'),
      component: (
        <AccessAsset
          protocol={protocol}
          objectId={objectId}
          initialState={wizardState.asset}
          onNext={handleAssetNext}
        />
      )
    },
    {
      title: t('monitor.integrations.flow.accessGuide'),
      component: wizardState.asset ? (
        <AccessGuide
          protocol={protocol}
          objectId={objectId}
          assetState={wizardState.asset}
          onNext={handleGuideNext}
          onPrev={handlePrev}
        />
      ) : null
    },
    {
      title: t('monitor.integrations.flow.accessComplete'),
      component: <AccessComplete onReset={handleReset} />
    }
  ];

  return (
    <div className="w-full">
      <div className="p-[10px]">
        <div className="mb-8 px-[20px]">
          <Steps current={currentStep} size="default">
            {steps.map((step, index) => (
              <Steps.Step key={index} title={step.title} />
            ))}
          </Steps>
        </div>
        <div>{steps[currentStep].component}</div>
      </div>
    </div>
  );
};

export default FlowConfiguration;
