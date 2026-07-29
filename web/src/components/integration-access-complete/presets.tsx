import type {
  IntegrationAccessCompleteAction,
  IntegrationAccessCompleteProps,
} from './index';

type TranslateFn = (key: string) => string;

interface IntegrationAccessCompletePresetOptions {
  onPrimaryAction: () => void;
  onSecondaryAction: () => void;
}

interface IntegrationAccessCompleteTertiaryPresetOptions
  extends IntegrationAccessCompletePresetOptions {
  onTertiaryAction: () => void;
}

interface IntegrationAccessCompletePreset
  extends Pick<
    IntegrationAccessCompleteProps,
    'title' | 'description' | 'subDescription' | 'primaryIconType' | 'statusIconType'
  > {
  actions: IntegrationAccessCompleteAction[];
}

export const createMonitorK8sAccessCompletePreset = (
  t: TranslateFn,
  { onPrimaryAction, onSecondaryAction }: IntegrationAccessCompletePresetOptions,
): IntegrationAccessCompletePreset => ({
  title: t('monitor.integrations.k8s.accessCompleteTitle'),
  description: t('monitor.integrations.k8s.accessCompleteDesc'),
  subDescription: t('monitor.integrations.k8s.accessCompleteSubDesc'),
  actions: [
    {
      key: 'primary',
      label: t('monitor.integrations.k8s.viewClusterList'),
      type: 'primary',
      onClick: onPrimaryAction,
    },
    {
      key: 'secondary',
      label: t('monitor.integrations.k8s.addAnotherCluster'),
      onClick: onSecondaryAction,
    },
  ],
});

export const createLogK8sAccessCompletePreset = (
  t: TranslateFn,
  { onPrimaryAction, onSecondaryAction }: IntegrationAccessCompletePresetOptions,
): IntegrationAccessCompletePreset => ({
  title: t('log.integration.k8s.accessCompleteTitle'),
  description: t('log.integration.k8s.accessCompleteDesc'),
  subDescription: t('log.integration.k8s.accessCompleteSubDesc'),
  primaryIconType: 'duihaochenggong',
  statusIconType: 'duihaochenggong',
  actions: [
    {
      key: 'primary',
      label: t('log.integration.k8s.viewClusterList'),
      type: 'primary',
      onClick: onPrimaryAction,
    },
    {
      key: 'secondary',
      label: t('log.integration.k8s.addAnotherCluster'),
      onClick: onSecondaryAction,
    },
  ],
});

export const createCmdbK8sAccessCompletePreset = (
  t: TranslateFn,
  { onPrimaryAction, onSecondaryAction }: IntegrationAccessCompletePresetOptions,
): IntegrationAccessCompletePreset => ({
  title: t('Collection.k8sTask.accessCompleteTitle') || 'Collector setup completed',
  description:
    t('Collection.k8sTask.accessCompleteDesc') ||
    'The collector is reporting to VictoriaMetrics. CMDB will materialize k8s resources (nodes / pods / workloads / namespaces) on the configured schedule. Open the task detail to trigger a one-off run if needed.',
  actions: [
    {
      key: 'done',
      label: t('common.done') || 'Done',
      type: 'primary',
      onClick: onPrimaryAction,
    },
    {
      key: 'another',
      label: t('Collection.k8sTask.addAnotherCluster') || 'Add another cluster',
      onClick: onSecondaryAction,
    },
  ],
});

export const createMonitorFlowAccessCompletePreset = (
  t: TranslateFn,
  {
    onPrimaryAction,
    onSecondaryAction,
    onTertiaryAction,
  }: IntegrationAccessCompleteTertiaryPresetOptions,
): IntegrationAccessCompletePreset => ({
  title: t('monitor.integrations.flow.accessCompleteTitle'),
  description: t('monitor.integrations.flow.accessCompleteDesc'),
  subDescription: t('monitor.integrations.flow.accessCompleteSubDesc'),
  actions: [
    {
      key: 'primary',
      label: t('monitor.integrations.flow.viewAssetList'),
      type: 'primary',
      onClick: onPrimaryAction,
    },
    {
      key: 'another',
      label: t('monitor.integrations.flow.addAnotherAsset'),
      onClick: onSecondaryAction,
    },
    {
      key: 'back',
      label: t('monitor.integrations.flow.backToTemplateList'),
      onClick: onTertiaryAction,
    },
  ],
});
