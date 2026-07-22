import React from 'react';
import IntegrationAccessComplete, {
  type IntegrationAccessCompleteProps,
} from '@/components/integration-access-complete';
import StepWizardFlow, {
  type StepWizardFlowStep,
} from '@/components/step-wizard-flow';

interface IntegrationK8sConfigurationShellState<TData> {
  commandData: TData | null;
}

interface IntegrationK8sConfigurationShellProps<TData> {
  initialCommandData?: TData | null;
  accessConfigTitle: React.ReactNode;
  collectorInstallTitle: React.ReactNode;
  accessCompleteTitle: React.ReactNode;
  renderAccessConfig: (args: {
    commandData: TData | null;
    next: (
      updater?: TData | null | ((current: TData | null) => TData | null)
    ) => void;
  }) => React.ReactNode;
  renderCollectorInstall: (args: {
    commandData: TData | null;
    prev: () => void;
    next: (
      updater?: TData | null | ((current: TData | null) => TData | null)
    ) => void;
  }) => React.ReactNode;
  accessCompletePreset: IntegrationAccessCompleteProps;
  resetActionKey?: string;
  className?: string;
}

const IntegrationK8sConfigurationShell = <TData,>({
  initialCommandData = null,
  accessConfigTitle,
  collectorInstallTitle,
  accessCompleteTitle,
  renderAccessConfig,
  renderCollectorInstall,
  accessCompletePreset,
  resetActionKey = 'secondary',
  className,
}: IntegrationK8sConfigurationShellProps<TData>) => {
  const resolveCommandData = (
    currentCommandData: TData | null,
    updater?: TData | null | ((current: TData | null) => TData | null)
  ) => {
    if (typeof updater === 'function') {
      return (updater as (current: TData | null) => TData | null)(
        currentCommandData
      );
    }

    return updater ?? currentCommandData;
  };

  const steps: StepWizardFlowStep<
    IntegrationK8sConfigurationShellState<TData>
  >[] = [
    {
      title: accessConfigTitle,
      content: ({ state, next }) =>
        renderAccessConfig({
          commandData: state.commandData,
          next: (updater) =>
            next((current) => ({
              ...current,
              commandData: resolveCommandData(current.commandData, updater),
            })),
        }),
    },
    {
      title: collectorInstallTitle,
      content: ({ state, next, prev }) =>
        renderCollectorInstall({
          commandData: state.commandData,
          prev,
          next: (updater) =>
            next((current) => ({
              ...current,
              commandData: resolveCommandData(current.commandData, updater),
            })),
        }),
    },
    {
      title: accessCompleteTitle,
      content: ({ reset }) => {
        const preset = {
          ...accessCompletePreset,
          actions: accessCompletePreset.actions.map((action) => {
            if (action.key !== resetActionKey) {
              return action;
            }

            return {
              ...action,
              onClick: () => reset({ commandData: initialCommandData }),
            };
          }),
        };

        return (
          <IntegrationAccessComplete
            title={preset.title}
            description={preset.description}
            subDescription={preset.subDescription}
            primaryIconType={preset.primaryIconType}
            statusIconType={preset.statusIconType}
            actions={preset.actions}
          />
        );
      },
    },
  ];

  return (
    <StepWizardFlow
      className={className}
      initialState={{ commandData: initialCommandData }}
      steps={steps}
    />
  );
};

export default IntegrationK8sConfigurationShell;
