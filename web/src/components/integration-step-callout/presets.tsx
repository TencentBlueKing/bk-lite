import type { IntegrationStepCalloutProps } from './index';

type TranslateFn = (key: string) => string;

export type IntegrationStepCalloutPreset = Pick<
  IntegrationStepCalloutProps,
  'title' | 'description' | 'items'
>;

export const createMonitorK8sStepCalloutPreset = (
  t: TranslateFn,
): IntegrationStepCalloutPreset => ({
  title: t('monitor.integrations.k8s.prerequisites'),
  description: t('monitor.integrations.k8s.prerequisitesDesc'),
  items: [
    t('monitor.integrations.k8s.k8sVersionRequirement'),
    t('monitor.integrations.k8s.resourceRequirement'),
    t('monitor.integrations.k8s.permissionRequirement'),
  ],
});

export const createLogK8sStepCalloutPreset = (
  t: TranslateFn,
): IntegrationStepCalloutPreset => ({
  title: t('log.integration.k8s.prerequisites'),
  description: t('log.integration.k8s.prerequisitesDesc'),
  items: [
    t('log.integration.k8s.k8sVersionRequirement'),
    t('log.integration.k8s.resourceRequirement'),
    t('log.integration.k8s.permissionRequirement'),
    t('log.integration.k8s.presetHint'),
  ],
});
