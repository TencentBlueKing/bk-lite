'use client';
import React, { useState } from 'react';
import { Steps } from 'antd';
import { useTranslation } from '@/utils/i18n';
import AccessConfig from './accessConfig';
import CollectorInstall from './collectorInstall';
import AccessComplete from './accessComplete';

const K8sConfiguration: React.FC = () => {
  const { t } = useTranslation();
  const [currentStep, setCurrentStep] = useState(0);
  const [commandData, setCommandData] = useState<any>(null);

  const handleNext = (data?: any) => {
    if (data) {
      setCommandData(data);
    }
    setCurrentStep(currentStep + 1);
  };

  const handlePrev = () => {
    setCurrentStep(currentStep - 1);
  };

  const handleReset = () => {
    setCurrentStep(0);
    setCommandData(null);
  };

  const steps = [
    {
      title: t('monitor.integrations.k8s.accessConfig'),
      component: <AccessConfig onNext={handleNext} commandData={commandData} />,
    },
    {
      title: t('monitor.integrations.k8s.collectorInstall'),
      component: (
        <CollectorInstall
          onNext={handleNext}
          onPrev={handlePrev}
          commandData={commandData}
        />
      ),
    },
    {
      title: t('monitor.integrations.k8s.accessComplete'),
      component: <AccessComplete onReset={handleReset} />,
    },
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

export default K8sConfiguration;
