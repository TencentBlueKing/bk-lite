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

export interface InstallerFailureContext {
  bucket?: string;
  file_key?: string;
  package_name?: string;
  cpu_architecture?: string;
  install_dir?: string;
  target_path?: string;
  exit_code?: number;
}

export interface InstallerFailure {
  message?: string;
  type?: string;
  code?: number;
  summary?: string;
  context?: InstallerFailureContext;
  retriable?: boolean;
  raw_error?: string;
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
  failure?: InstallerFailure;
}

export interface InstallerProgressSummary {
  current_step?: InstallerStepCode;
  current_status?: InstallerTaskStatus;
  current_message?: string;
  progress?: InstallerProgressMetric;
  step_index?: number;
  step_total?: number;
}

export interface InstallerEventSummary {
  state?: string;
  expected_steps?: InstallerStepCode[];
  expected_count?: number;
  observed_count?: number;
  completed_steps?: InstallerStepCode[];
  completed_count?: number;
  missing_steps?: InstallerStepCode[];
  duplicate_count?: number;
  last_step?: InstallerStepCode | null;
  last_status?: InstallerTaskStatus | null;
  anomalies?: string[];
  steps?: LogStep[];
}

export interface OperationTaskResult {
  steps?: LogStep[];
  installer_progress?: InstallerProgressSummary;
  installer_summary?: InstallerEventSummary;
  failure?: InstallerFailure;
}

export interface ControllerInstallProgressRow {
  id?: string | number;
  ip?: string;
  node_name?: string;
  node_id?: string | number;
  task_node_id?: string | number;
  os?: string;
  cpu_architecture?: string;
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
  cpu_architecture?: string;
}
export interface ManualInstallController {
  cloud_region_id?: React.Key;
  os?: string;
  cpu_architecture?: string;
  package_id?: React.Key;
  nodes?: NodeItem[];
}

export interface OperationGuidanceProps {
  ip: string;
  nodeName: string;
  installerSession?: string;
  os?: string;
  cpu_architecture?: string;
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
