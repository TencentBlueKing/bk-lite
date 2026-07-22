import React, { useCallback, useState } from 'react';
import StepWizardLayout from './layout';

export interface StepWizardFlowContext<TState> {
  currentStep: number;
  state: TState;
  next: (nextState?: React.SetStateAction<TState>) => void;
  prev: () => void;
  goTo: (step: number) => void;
  reset: (nextState?: TState) => void;
  setState: React.Dispatch<React.SetStateAction<TState>>;
}

export interface StepWizardFlowStep<TState> {
  title: React.ReactNode;
  content: (context: StepWizardFlowContext<TState>) => React.ReactNode;
}

export interface StepWizardFlowProps<TState> {
  initialState: TState;
  steps: StepWizardFlowStep<TState>[];
  className?: string;
}

const StepWizardFlow = <TState,>({
  initialState,
  steps,
  className,
}: StepWizardFlowProps<TState>) => {
  const [currentStep, setCurrentStep] = useState(0);
  const [state, setState] = useState(initialState);

  const next = useCallback((nextState?: React.SetStateAction<TState>) => {
    if (nextState !== undefined) {
      setState(nextState);
    }
    setCurrentStep((prev) => Math.min(prev + 1, steps.length - 1));
  }, [steps.length]);

  const prev = useCallback(() => {
    setCurrentStep((prevStep) => Math.max(prevStep - 1, 0));
  }, []);

  const goTo = useCallback((step: number) => {
    setCurrentStep(Math.min(Math.max(step, 0), steps.length - 1));
  }, [steps.length]);

  const reset = useCallback((nextState?: TState) => {
    setCurrentStep(0);
    setState(nextState ?? initialState);
  }, [initialState]);

  const context: StepWizardFlowContext<TState> = {
    currentStep,
    state,
    next,
    prev,
    goTo,
    reset,
    setState,
  };

  return (
    <div className={className}>
      <StepWizardLayout
        currentStep={currentStep}
        steps={steps.map((step) => ({
          title: step.title,
          content: step.content(context),
        }))}
      />
    </div>
  );
};

export default StepWizardFlow;
