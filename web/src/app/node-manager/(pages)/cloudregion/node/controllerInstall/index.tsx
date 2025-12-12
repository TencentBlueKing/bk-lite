'use client';
import React, { useState } from 'react';
import { Steps } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { ControllerInstallProps } from '@/app/node-manager/types/cloudregion';
import InstallConfig from './installConfig';
import Installing from './installing';
import InstallComplete from './installComplete';

const ControllerInstall: React.FC<ControllerInstallProps> = ({ cancel }) => {
  const { t } = useTranslation();
  const [currentStep, setCurrentStep] = useState(0);
  const [installData, setInstallData] = useState<any>(null);

  const handleNextStep = (data?: any) => {
    if (data) {
      setInstallData(data);
    }
    setCurrentStep((prev) => prev + 1);
  };

  const handleReset = () => {
    setCurrentStep(0);
    setInstallData(null);
  };

  const steps = [
    {
      title: t('node-manager.controller.installConfig'),
      component: <InstallConfig onNext={handleNextStep} cancel={cancel} />,
    },
    {
      title: t('node-manager.controller.installing'),
      component: (
        <Installing
          onNext={handleNextStep}
          cancel={cancel}
          installData={installData}
        />
      ),
    },
    {
      title: t('node-manager.controller.installComplete'),
      component: <InstallComplete onReset={handleReset} onFinish={cancel} />,
    },
  ];

  return (
    <div className="w-[calc(100vw-280px)]">
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
    </div>
  );
};

export default ControllerInstall;
