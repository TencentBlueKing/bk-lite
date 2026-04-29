import React from 'react';

export interface ControllerCardProps {
  id: string;
  name: string;
  system?: string[];
  introduction: string;
  icon: string;
}

export interface LogStep {
  action: string;
  status: InstallerTaskStatus;
  message: string;
  timestamp: string;
  details?: InstallerStepDetails;
}

export type InstallerTaskStatus =
  | 'success'
  | 'error'
  | 'timeout'
  | 'running'
  | 'waiting'
  | 'installing'
  | 'installed'
  | (string & {});

export type InstallerStepCode =
  | 'fetch_session'
  | 'prepare_dirs'
  | 'prepare_directories'
  | 'download'
  | 'download_package'
  | 'extract'
  | 'extract_package'
  | 'write_config'
  | 'configure_runtime'
  | 'install'
  | 'run_package_installer'
  | 'install_complete'
  | 'complete'
  | (string & {});

export type InstallerStepLabelMap = Partial<
  Record<InstallerStepCode, string>
>;

export interface InstallerProgressMetric {
  percent?: number;
  current?: number;
  total?: number;
  unit?: string;
}

export interface InstallerStepDetails {
  installer_event?: boolean;
  raw_step?: InstallerStepCode;
  step_index?: number;
  step_total?: number;
  progress?: InstallerProgressMetric;
  timestamp?: string;
  error?: string;
  installer_message?: string;
}

export interface InstallerProgressSummary {
  current_step?: InstallerStepCode;
  current_status?: InstallerTaskStatus;
  current_message?: string;
  progress?: InstallerProgressMetric;
  step_index?: number;
  step_total?: number;
}

export interface OperationTaskResult {
  steps?: LogStep[];
  installer_progress?: InstallerProgressSummary;
}

export interface ControllerInstallProgressRow {
  id?: string | number;
  ip?: string;
  node_name?: string;
  node_id?: string | number;
  task_node_id?: string | number;
  os?: string;
  organizations?: string[];
  status?: InstallerTaskStatus | null;
  result?: OperationTaskResult | null;
}

export interface ControllerManualInstallStatusItem {
  node_id: React.Key;
  status: InstallerTaskStatus | null;
  result: OperationTaskResult | null;
}

export interface StatusConfig {
  text: string;
  tagColor: 'success' | 'error' | 'processing' | 'warning';
  borderColor: string;
  stepStatus: 'finish';
  icon: React.ReactNode;
}

export interface RetryInstallParams {
  task_id?: React.Key;
  task_node_ids?: React.Key[];
  password?: string;
  port?: string | number;
  username?: string;
  private_key?: string;
}

export interface InstallingProps {
  onNext: () => void;
  cancel: () => void;
  installData: any;
}

export interface NodeItem {
  ip: string;
  node_name: string;
  organizations: React.Key[];
  node_id: string;
}
export interface ManualInstallController {
  cloud_region_id?: React.Key;
  os?: string;
  package_id?: React.Key;
  nodes?: NodeItem[];
}

export interface OperationGuidanceProps {
  ip: string;
  nodeName: string;
  installerSession?: string;
  os?: string;
  installerVersion?: string;
  defaultInstallerVersion?: string;
  nodeData?: any;
}

export interface InstallerArtifactMetadata {
  os: string;
  cpu_architecture?: string;
  architecture?: string;
  filename: string;
  version: string;
  object_key: string;
  alias_object_key: string;
  download_url: string;
}

export interface InstallerManifest {
  default_version: string;
  artifacts: Record<string, Record<string, InstallerArtifactMetadata>>;
}
