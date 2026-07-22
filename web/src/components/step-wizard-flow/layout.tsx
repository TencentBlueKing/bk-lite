import React from 'react';
import { Steps } from 'antd';

export interface StepWizardItem {
  title: React.ReactNode;
  content: React.ReactNode;
}

interface StepWizardLayoutProps {
  currentStep: number;
  steps: StepWizardItem[];
}

const StepWizardLayout: React.FC<StepWizardLayoutProps> = ({
  currentStep,
  steps,
}) => {
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
        <div>{steps[currentStep]?.content}</div>
      </div>
    </div>
  );
};

export default StepWizardLayout;
