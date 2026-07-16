import type { K8sAccessAssetFieldsCopy } from './index';

type TranslateFn = (key: string) => string;

export const createMonitorK8sAccessAssetFieldsCopy = (
  t: TranslateFn,
): K8sAccessAssetFieldsCopy => ({
  accessAsset: t('monitor.integrations.k8s.accessAsset'),
  accessAssetDesc: t('monitor.integrations.k8s.accessAssetDesc'),
  newAsset: t('monitor.integrations.k8s.newAsset'),
  existingAsset: t('monitor.integrations.k8s.existingAsset'),
  clusterName: t('monitor.integrations.k8s.clusterName'),
  clusterNamePlaceholder: t('common.inputTip'),
  clusterNameDesc: t('monitor.integrations.k8s.clusterNameDesc'),
  organization: t('monitor.integrations.k8s.organization'),
  organizationDesc: t('monitor.integrations.k8s.organizationDesc'),
  k8sCluster: t('monitor.integrations.k8s.k8sCluster'),
  k8sClusterDesc: t('monitor.integrations.k8s.k8sClusterDesc'),
  selectClusterPlaceholder: t('common.selectTip'),
  cloudRegion: t('monitor.integrations.k8s.cloudRegion'),
  cloudRegionDesc: t('monitor.integrations.k8s.cloudRegionDesc'),
  selectCloudRegionPlaceholder: t('common.selectTip'),
  requiredMessage: t('common.required'),
  selectTip: t('common.selectTip'),
});

export const createLogK8sAccessAssetFieldsCopy = (
  t: TranslateFn,
): K8sAccessAssetFieldsCopy => ({
  accessAsset: t('log.integration.k8s.accessAsset'),
  accessAssetDesc: t('log.integration.k8s.accessAssetDesc'),
  newAsset: t('log.integration.k8s.newAsset'),
  existingAsset: t('log.integration.k8s.existingAsset'),
  clusterName: t('log.integration.k8s.clusterName'),
  clusterNamePlaceholder: t('log.integration.k8s.clusterNamePlaceholder'),
  clusterNameDesc: t('log.integration.k8s.clusterNameDesc'),
  organization: t('log.integration.k8s.organization'),
  organizationDesc: t('log.integration.k8s.organizationDesc'),
  k8sCluster: t('log.integration.k8s.k8sCluster'),
  k8sClusterDesc: t('log.integration.k8s.k8sClusterDesc'),
  selectClusterPlaceholder: t('log.integration.k8s.selectK8sCluster'),
  cloudRegion: t('log.integration.k8s.cloudRegion'),
  cloudRegionDesc: t('log.integration.k8s.cloudRegionDesc'),
  selectCloudRegionPlaceholder: t('log.integration.k8s.selectCloudRegion'),
  requiredMessage: t('common.required'),
  selectTip: t('common.selectTip'),
});
