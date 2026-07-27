const k8sStoryTranslations: Record<string, string> = {
  'monitor.integrations.k8s.accessCompleteTitle': 'Cluster setup completed',
  'monitor.integrations.k8s.accessCompleteDesc':
    'The collector is reporting and the integration is ready for the next workflow step.',
  'monitor.integrations.k8s.accessCompleteSubDesc':
    'You can review the discovered clusters now or start another guided setup.',
  'monitor.integrations.k8s.viewClusterList': 'View clusters',
  'monitor.integrations.k8s.addAnotherCluster': 'Add another cluster',
  'log.integration.k8s.accessCompleteTitle': 'Log collector connected',
  'log.integration.k8s.accessCompleteDesc':
    'The collector is reporting and log ingestion is ready to continue.',
  'log.integration.k8s.accessCompleteSubDesc':
    'Open the receive list now or start another cluster onboarding flow.',
  'log.integration.k8s.viewClusterList': 'View receive list',
  'log.integration.k8s.addAnotherCluster': 'Add another cluster',
  'Collection.k8sTask.accessCompleteTitle': 'Collector setup completed',
  'Collection.k8sTask.accessCompleteDesc':
    'The collector is reporting. CMDB will materialize k8s resources on the configured schedule.',
  'Collection.k8sTask.addAnotherCluster': 'Add another cluster',
  'Collection.k8sTask.installCollector': 'Install Collector',
  'Collection.k8sTask.installCommandDesc':
    'Generate a short-lived install token, then copy and run the command on a host with kubectl access to the target cluster.',
  'Collection.k8sTask.verifyStatus': 'Verify Reporting',
  'Collection.k8sTask.verify': 'Verify',
  'Collection.k8sTask.verifyWaitingDesc':
    'After deploying the YAML, click verify; CMDB will query VictoriaMetrics for the configured collector id.',
  'Collection.k8sTask.verifySuccess': 'Collector is reporting',
  'Collection.k8sTask.verifySuccessDesc':
    'Metrics received. CMDB resource discovery will run on the configured schedule.',
  'Collection.k8sTask.verifyFailed': 'Not reporting yet',
  'Collection.k8sTask.verifyFailedDesc':
    'Verify the YAML was applied and that the cluster can reach the configured NATS endpoint.',
  'monitor.integrations.flow.accessCompleteTitle': 'Flow integration completed',
  'monitor.integrations.flow.accessCompleteDesc':
    'The sampled flow data is available and the onboarding flow can return to the template list.',
  'monitor.integrations.flow.accessCompleteSubDesc':
    'Review the discovered assets, add another source, or go back to the integration catalog.',
  'monitor.integrations.flow.viewAssetList': 'View assets',
  'monitor.integrations.flow.addAnotherAsset': 'Add another asset',
  'monitor.integrations.flow.backToTemplateList': 'Back to template list',
  'monitor.integrations.k8s.prerequisites': 'Prerequisites',
  'monitor.integrations.k8s.prerequisitesDesc':
    'Confirm the target cluster is ready before generating the install command.',
  'monitor.integrations.k8s.k8sVersionRequirement':
    'Kubernetes version meets the minimum requirement',
  'monitor.integrations.k8s.resourceRequirement':
    'Worker resources satisfy the collector footprint',
  'monitor.integrations.k8s.permissionRequirement':
    'Required RBAC permissions are available',
  'log.integration.k8s.prerequisites': 'Prerequisites',
  'log.integration.k8s.prerequisitesDesc':
    'Validate the cluster baseline before generating the collector command and log path preset.',
  'log.integration.k8s.k8sVersionRequirement':
    'Kubernetes version meets the minimum requirement',
  'log.integration.k8s.resourceRequirement':
    'Worker resources satisfy the collector footprint',
  'log.integration.k8s.permissionRequirement':
    'Required RBAC permissions are available',
  'log.integration.k8s.presetHint':
    'Choose a runtime preset that matches the node log layout',
  'monitor.integrations.k8s.accessAsset': 'Access asset',
  'monitor.integrations.k8s.accessAssetDesc':
    'Choose whether to create a new cluster asset or bind an existing one.',
  'monitor.integrations.k8s.newAsset': 'New asset',
  'monitor.integrations.k8s.existingAsset': 'Existing asset',
  'monitor.integrations.k8s.clusterName': 'Cluster name',
  'monitor.integrations.k8s.clusterNameDesc':
    'This name will be used when the integration creates a new managed asset.',
  'monitor.integrations.k8s.organization': 'Organization',
  'monitor.integrations.k8s.organizationDesc':
    'Choose the owning organization for the created cluster asset.',
  'monitor.integrations.k8s.k8sCluster': 'K8s cluster',
  'monitor.integrations.k8s.k8sClusterDesc':
    'Reuse an existing cluster asset when it already exists in inventory.',
  'monitor.integrations.k8s.cloudRegion': 'Cloud region',
  'monitor.integrations.k8s.cloudRegionDesc':
    'Commands are generated against the selected cloud region.',
  'monitor.integrations.k8s.installCollector': 'Install collector',
  'monitor.integrations.k8s.installCommandDesc':
    'Run the generated command on your target cluster to deploy the collector.',
  'monitor.integrations.k8s.verifyStatus': 'Verify status',
  'monitor.integrations.k8s.verify': 'Verify',
  'monitor.integrations.k8s.verifyWaitingDesc':
    'Waiting for the collector to report back.',
  'monitor.integrations.k8s.verifySuccess': 'Collector verified',
  'monitor.integrations.k8s.verifySuccessDesc':
    'The cluster is now connected and ready for the next step.',
  'monitor.integrations.k8s.verifyFailed': 'Verification failed',
  'monitor.integrations.k8s.verifyFailedDesc':
    'The collector did not report back successfully. Review',
  'monitor.integrations.k8s.commonIssues': 'common issues',
  'monitor.integrations.k8s.troubleshoot':
    'and retry once the environment is fixed.',
  'log.integration.k8s.accessAsset': 'Access asset',
  'log.integration.k8s.accessAssetDesc':
    'Choose whether to bind an existing cluster or create one for log collection.',
  'log.integration.k8s.newAsset': 'New asset',
  'log.integration.k8s.existingAsset': 'Existing asset',
  'log.integration.k8s.clusterName': 'Cluster name',
  'log.integration.k8s.clusterNamePlaceholder': 'Enter cluster name',
  'log.integration.k8s.clusterNameDesc':
    'This cluster identity is used when log onboarding creates a new managed asset.',
  'log.integration.k8s.organization': 'Organization',
  'log.integration.k8s.organizationDesc':
    'Select the team that owns the log-collection cluster asset.',
  'log.integration.k8s.k8sCluster': 'K8s cluster',
  'log.integration.k8s.k8sClusterDesc':
    'Reuse an existing cluster asset when log collection is already attached to inventory.',
  'log.integration.k8s.selectK8sCluster': 'Select existing cluster',
  'log.integration.k8s.cloudRegion': 'Cloud region',
  'log.integration.k8s.cloudRegionDesc':
    'The selected cloud region controls generated commands and runtime presets.',
  'log.integration.k8s.selectCloudRegion': 'Select cloud region',
  'log.integration.k8s.installCollector': 'Install collector',
  'log.integration.k8s.installCommandDesc':
    'Run the generated command on your target cluster to deploy the collector.',
  'log.integration.k8s.verifyStatus': 'Verify status',
  'log.integration.k8s.verify': 'Verify',
  'log.integration.k8s.verifyWaitingDesc':
    'Waiting for the collector to report back.',
  'log.integration.k8s.verifySuccess': 'Collector verified',
  'log.integration.k8s.verifySuccessDesc':
    'The collector is now connected and ready for the next step.',
  'log.integration.k8s.verifyFailed': 'Verification failed',
  'log.integration.k8s.verifyFailedDesc':
    'The collector did not report back successfully. Review',
  'log.integration.k8s.commonIssues': 'common issues',
  'log.integration.k8s.troubleshoot':
    'and retry once the log path and network are fixed.',
  'log.integration.k8s.reasonLabel': 'Reason: ',
  'log.integration.k8s.solutionLabel': 'Solutions',
  'log.integration.k8s.commonIssuePendingTitle':
    'Pod pending for a long time',
  'log.integration.k8s.commonIssuePendingReason':
    'The cluster has no schedulable resources.',
  'log.integration.k8s.commonIssuePendingSolution1':
    'Check node usage with kubectl top nodes.',
  'log.integration.k8s.commonIssuePendingSolution2':
    'Reduce requests or add worker nodes.',
  'log.integration.k8s.commonIssueNatsTitle':
    'Collector cannot reach NATS',
  'log.integration.k8s.commonIssueNatsReason':
    'Network or certificate setup is blocking the connection.',
  'log.integration.k8s.commonIssueNatsSolution1':
    'Inspect collector pod logs for connection errors.',
  'log.integration.k8s.commonIssueNatsSolution2':
    'Verify the cluster can reach the configured NATS endpoint.',
  'log.integration.k8s.commonIssueMountTitle':
    'Log mount path is unavailable',
  'log.integration.k8s.commonIssueMountReason':
    'The configured host or container path is not mounted into the collector.',
  'log.integration.k8s.commonIssueMountSolution1':
    'Check the generated YAML volumeMount and hostPath settings.',
  'log.integration.k8s.commonIssueMountSolution2':
    'Verify the target log path exists on the node or container runtime.',
  'common.done': 'Done',
  'common.inputTip': 'Enter value',
  'common.selectTip': 'Select an option',
  'common.required': 'Required',
  'common.pre': 'Previous',
};

export const createK8sStoryT = (
  overrides: Record<string, string> = {},
) => {
  const translations = {
    ...k8sStoryTranslations,
    ...overrides,
  };

  return (key: string) => translations[key] || key;
};
