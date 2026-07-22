import type { K8sCollectorInstallStepCopy } from './index';

type TranslateFn = (key: string) => string;

export const createMonitorK8sCollectorInstallCopy = (
  t: TranslateFn,
): K8sCollectorInstallStepCopy => ({
  title: t('monitor.integrations.k8s.installCollector'),
  installDescription: t('monitor.integrations.k8s.installCommandDesc'),
  verifyTitle: t('monitor.integrations.k8s.verifyStatus'),
  verifyButtonText: t('monitor.integrations.k8s.verify'),
  verifyWaitingDescription: t('monitor.integrations.k8s.verifyWaitingDesc'),
  prevButtonText: t('common.pre'),
  successMessage: t('monitor.integrations.k8s.verifySuccess'),
  successDescription: t('monitor.integrations.k8s.verifySuccessDesc'),
  failedMessage: t('monitor.integrations.k8s.verifyFailed'),
  failedDescription: t('monitor.integrations.k8s.verifyFailedDesc'),
  commonIssuesText: t('monitor.integrations.k8s.commonIssues'),
  troubleshootText: t('monitor.integrations.k8s.troubleshoot'),
  verifyFailedToast: t('monitor.integrations.k8s.verifyFailed'),
});

export const createLogK8sCollectorInstallCopy = (
  t: TranslateFn,
): K8sCollectorInstallStepCopy => ({
  title: t('log.integration.k8s.installCollector'),
  installDescription: t('log.integration.k8s.installCommandDesc'),
  verifyTitle: t('log.integration.k8s.verifyStatus'),
  verifyButtonText: t('log.integration.k8s.verify'),
  verifyWaitingDescription: t('log.integration.k8s.verifyWaitingDesc'),
  prevButtonText: t('common.pre'),
  successMessage: t('log.integration.k8s.verifySuccess'),
  successDescription: t('log.integration.k8s.verifySuccessDesc'),
  failedMessage: t('log.integration.k8s.verifyFailed'),
  failedDescription: t('log.integration.k8s.verifyFailedDesc'),
  commonIssuesText: t('log.integration.k8s.commonIssues'),
  troubleshootText: t('log.integration.k8s.troubleshoot'),
  verifyFailedToast: t('log.integration.k8s.verifyFailed'),
});

export const createCmdbK8sCollectorInstallCopy = (
  t: TranslateFn,
): K8sCollectorInstallStepCopy => ({
  title: t('Collection.k8sTask.installCollector') || 'Install Collector',
  installDescription:
    t('Collection.k8sTask.installCommandDesc') ||
    'Generate a short-lived install token, then copy and run the command on a host with kubectl access to the target cluster.',
  verifyTitle: t('Collection.k8sTask.verifyStatus') || 'Verify Reporting',
  verifyButtonText: t('Collection.k8sTask.verify') || 'Verify',
  verifyWaitingDescription:
    t('Collection.k8sTask.verifyWaitingDesc') ||
    'After deploying the YAML, click verify; CMDB will query VictoriaMetrics for the configured collector id.',
  prevButtonText: t('common.pre') || 'Previous',
  successMessage:
    t('Collection.k8sTask.verifySuccess') || 'Collector is reporting',
  successDescription:
    t('Collection.k8sTask.verifySuccessDesc') ||
    'Metrics received. CMDB resource discovery will run on the configured schedule.',
  failedMessage: t('Collection.k8sTask.verifyFailed') || 'Not reporting yet',
  failedDescription:
    t('Collection.k8sTask.verifyFailedDesc') ||
    'Verify the YAML was applied and that the cluster can reach the configured NATS endpoint.',
  verifyFailedToast:
    t('Collection.k8sTask.verifyFailed') ||
    'Collector not reporting yet, retry in a moment.',
});
