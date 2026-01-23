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
  status: string;
  message: string;
  timestamp: string;
}

export interface StatusConfig {
  text: string;
  tagColor: 'success' | 'error' | 'processing';
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
  installCommand?: string;
  downloadUrl?: string;
  nodeData?: any;
}
